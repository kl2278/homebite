"""Plain Python tools the agents can call. Nutrition math and allergen checks happen here, in code."""

import csv
import difflib
import re
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel

DATA_DIR = Path(__file__).resolve().parent / "data"
NUTRITION_PATH = DATA_DIR / "nutrition.csv"
CATALOG_PATH = DATA_DIR / "grocery_catalog.csv"

ALLERGENS = ["peanuts", "tree_nuts", "shellfish", "fish", "soy", "wheat_gluten", "eggs", "dairy", "sesame"]
NUTRIENT_COLUMNS = ["kcal", "protein_g", "fat_g", "carbs_g", "fiber_g", "sugar_g", "sodium_mg"]


# ---------------------------------------------------------------- models

class NutritionItem(BaseModel):
    """One food with nutrition values per 100 g. None means USDA did not report it."""

    fdc_id: int
    description: str
    kcal: float | None
    protein_g: float | None
    fat_g: float | None
    carbs_g: float | None
    fiber_g: float | None
    sugar_g: float | None
    sodium_mg: float | None


class NutritionSearchResult(BaseModel):
    found: bool
    query: str
    matches: list[NutritionItem]


class NutritionBatchResult(BaseModel):
    """Results of several searches done in one call: one NutritionSearchResult per query, in order."""

    results: list[NutritionSearchResult]


class CatalogItem(BaseModel):
    store: str
    product_name: str
    category: str
    usda_match_description: str
    fdc_id: int | None  # links the product to nutrition.csv
    allergen_tags: list[str]
    price_usd: float
    verified: bool
    source_note: str


class CatalogSearchResult(BaseModel):
    found: bool
    store: str
    query: str
    items: list[CatalogItem]
    excluded_for_allergens: list[str]  # product names removed because of exclude_allergens
    note: str = ""


class IngredientAmount(BaseModel):
    fdc_id: int
    grams: float


class RecipeNutrition(BaseModel):
    found: bool  # True if at least one ingredient was found and counted
    servings: int
    per_serving: dict[str, float]
    total: dict[str, float]
    missing_fdc_ids: list[int]  # ingredients NOT counted because the fdc_id is unknown
    incomplete_nutrients: dict[str, list[int]]  # nutrient -> fdc_ids where USDA has no value
    error: str = ""


class AllergenConflict(BaseModel):
    ingredient: str
    allergen: str
    reason: str


class UncertainIngredient(BaseModel):
    ingredient: str
    reason: str


class AllergenCheck(BaseModel):
    conflicts: list[AllergenConflict]
    uncertain: list[UncertainIngredient]  # allergen status could not be determined
    cleared: list[str]  # ingredients positively known to avoid the listed allergens
    all_clear: bool  # True only if there are no conflicts AND nothing is uncertain
    invalid_allergens: list[str] = []


# ---------------------------------------------------------------- loading

def _number(text: str) -> float | None:
    return float(text) if text.strip() else None


@lru_cache
def _nutrition() -> dict[int, NutritionItem]:
    with NUTRITION_PATH.open(newline="", encoding="utf-8") as f:
        rows = csv.DictReader(f)
        return {
            int(r["fdc_id"]): NutritionItem(
                fdc_id=int(r["fdc_id"]),
                description=r["description"],
                **{c: _number(r[c]) for c in NUTRIENT_COLUMNS},
            )
            for r in rows
        }


@lru_cache
def _catalog() -> list[CatalogItem]:
    by_description = {item.description: item.fdc_id for item in _nutrition().values()}
    with CATALOG_PATH.open(newline="", encoding="utf-8") as f:
        return [
            CatalogItem(
                store=r["store"],
                product_name=r["product_name"],
                category=r["category"],
                usda_match_description=r["usda_match_description"],
                fdc_id=by_description.get(r["usda_match_description"]),
                allergen_tags=[t for t in r["allergen_tags"].split(";") if t],
                price_usd=float(r["price_usd"]),
                verified=r["verified"].strip().lower() == "true",
                source_note=r["source_note"],
            )
            for r in csv.DictReader(f)
        ]


def get_food(fdc_id: int) -> NutritionItem | None:
    """Look up one food by fdc_id (used by code, not registered as an agent tool)."""
    return _nutrition().get(fdc_id)


def find_catalog_item(product_name: str, store: str) -> CatalogItem | None:
    """Exact (case-insensitive) product lookup at one store (used by code, not an agent tool)."""
    for item in _catalog():
        if _normalize_store(item.store) == _normalize_store(store) and item.product_name.lower() == product_name.strip().lower():
            return item
    return None


# ---------------------------------------------------------------- fuzzy matching

def _stem(word: str) -> str:
    """Very light singularizing so 'lentils' matches 'lentil' and 'tomatoes' matches 'tomato'."""
    if len(word) > 4 and word.endswith("es"):
        word = word[:-2] if word.endswith(("oes", "ches", "shes", "sses")) else word[:-1]
    elif len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        word = word[:-1]
    return word


# Everyday names -> the names USDA uses.
SYNONYMS = {
    "bok choy": "pak choi", "daikon": "oriental radish", "cilantro": "coriander", "garbanzo": "chickpea",
    "scallion": "spring onion", "aubergine": "eggplant", "courgette": "zucchini", "yuca": "cassava",
    "bell pepper": "sweet pepper", "capsicum": "sweet pepper", "tamari": "soy sauce", "jaggery": "sugar",
}


def _words(text: str) -> list[str]:
    return [_stem(w) for w in re.findall(r"[a-z]+", text.lower())]


def _apply_synonyms(query: str) -> str:
    query = query.lower()
    for common, usda in SYNONYMS.items():
        query = query.replace(common, usda)
    return query


def _fix_typos(query_words: list[str], vocabulary: set[str]) -> list[str] | None:
    """Replace misspelled words with the closest known word; None if any word is unknown."""
    fixed = []
    for word in query_words:
        if word not in vocabulary:
            close = difflib.get_close_matches(word, vocabulary, n=1, cutoff=0.8)
            if not close:
                return None
            word = close[0]
        fixed.append(word)
    return fixed


# Filler words models like to add ("beef shank raw"); dropped only if the full query finds nothing.
FILLER_WORDS = {"raw", "uncooked", "fresh", "spice", "whole"}


def _match_all_words(query: str, texts: list[str]) -> list[int]:
    """Indexes of texts that contain every query word (after typo correction), best first."""
    word_sets = [set(_words(t)) for t in texts]
    vocabulary = set().union(*word_sets)
    query_words = _fix_typos(_words(_apply_synonyms(query)), vocabulary)
    if not query_words:
        return []
    hits = [i for i, words in enumerate(word_sets) if all(w in words for w in query_words)]
    if not hits:
        trimmed = [w for w in query_words if w not in FILLER_WORDS]
        if trimmed and trimmed != query_words:
            hits = [i for i, words in enumerate(word_sets) if all(w in words for w in trimmed)]
            query_words = trimmed

    def rank(i: int):
        words = _words(texts[i])
        head = _words(texts[i].split(",")[0])
        phrase_in_head = any(head[k:k + len(query_words)] == query_words for k in range(len(head)))
        return (
            "raw" not in words,  # raw foods are the best base for recipes
            not phrase_in_head,  # "soy sauce" beats "Sauce, peanut, made with soy sauce"
            bool(words) and words[0] not in query_words,  # starts with a query word
            len(head) - len(query_words),  # fewer extra words before the first comma ("Tofu yogurt")
            len(texts[i]),
        )

    return sorted(hits, key=rank)


# ---------------------------------------------------------------- tools

def search_nutrition(query: str, limit: int = 5) -> NutritionSearchResult:
    """Find foods in the bundled USDA nutrition table by name (fuzzy, typo tolerant).

    Args:
        query: Food name such as "tofu", "bok choy" or "chicken breast raw".
        limit: Maximum number of matches to return.

    Returns found=False with no matches if nothing in the table matches. Never guesses.
    Each match has fdc_id, description and per-100g values (kcal, protein_g, fat_g,
    carbs_g, fiber_g, sugar_g, sodium_mg). A value of null means USDA has no number.
    """
    items = list(_nutrition().values())
    order = _match_all_words(query, [i.description for i in items])
    matches = [items[i] for i in order[: max(limit, 0)]]
    return NutritionSearchResult(found=bool(matches), query=query, matches=matches)


def search_nutrition_many(queries: list[str], limit: int = 5) -> NutritionBatchResult:
    """Look up several foods in the USDA nutrition table in ONE call.

    Args:
        queries: Food names, for example ["beef chuck", "bok choy", "soy sauce"]. Same rules as search_nutrition.
        limit: Maximum matches per query.

    Returns one result per query, in the same order; each is exactly what search_nutrition would return.
    """
    return NutritionBatchResult(results=[search_nutrition(q, limit) for q in queries])


def _normalize_store(name: str) -> str:
    return re.sub(r"[^a-z]", "", name.lower())


def search_catalog(ingredient_query: str, store: str, exclude_allergens: list[str] | None = None) -> CatalogSearchResult:
    """Find products for an ingredient at one grocery store, leaving out listed allergens.

    Args:
        ingredient_query: Ingredient to look for, e.g. "tofu", "soy sauce", "rice".
        store: One of "Walmart", "Trader Joe's", "Whole Foods", "Aldi", "Asian grocery".
        exclude_allergens: Allergens to avoid, from: peanuts, tree_nuts, shellfish, fish,
            soy, wheat_gluten, eggs, dairy, sesame. Products tagged with any are removed.

    Returns found=False if the store is unknown or no product matches. Each item has its
    price and a verified flag (False means the entry has not been checked against a real store listing).
    """
    exclude = [a.lower() for a in (exclude_allergens or [])]
    store_items = [i for i in _catalog() if _normalize_store(i.store) == _normalize_store(store)]
    if not store_items:
        stores = sorted({i.store for i in _catalog()})
        return CatalogSearchResult(
            found=False, store=store, query=ingredient_query, items=[], excluded_for_allergens=[],
            note=f"Unknown store. Known stores: {', '.join(stores)}",
        )

    texts = [f"{i.product_name} {i.usda_match_description}" for i in store_items]
    matched = [store_items[k] for k in _match_all_words(ingredient_query, texts)]
    items = [i for i in matched if not set(i.allergen_tags) & set(exclude)]
    removed = [i.product_name for i in matched if i not in items]
    return CatalogSearchResult(
        found=bool(items), store=store_items[0].store, query=ingredient_query,
        items=items, excluded_for_allergens=removed,
    )


def compute_recipe_nutrition(ingredients: list[IngredientAmount], servings: int) -> RecipeNutrition:
    """Compute per-serving nutrition for a recipe, in code, from the USDA table.

    Args:
        ingredients: List of {fdc_id, grams}. Use fdc_id values from search_nutrition or search_catalog.
        servings: Number of servings the recipe makes (1 or more).

    Ingredients whose fdc_id is unknown are NOT counted and are listed in missing_fdc_ids.
    If USDA has no value for a nutrient (e.g. fiber), that ingredient adds nothing to that
    nutrient and is listed in incomplete_nutrients, so the total may be an underestimate.
    """
    if servings < 1:
        return RecipeNutrition(found=False, servings=servings, per_serving={}, total={}, missing_fdc_ids=[],
                               incomplete_nutrients={}, error="servings must be at least 1")
    if any(i.grams < 0 for i in ingredients):
        return RecipeNutrition(found=False, servings=servings, per_serving={}, total={}, missing_fdc_ids=[],
                               incomplete_nutrients={}, error="grams cannot be negative")

    table = _nutrition()
    total = {c: 0.0 for c in NUTRIENT_COLUMNS}
    missing: list[int] = []
    incomplete: dict[str, list[int]] = {}
    counted = 0
    for ingredient in ingredients:
        food = table.get(ingredient.fdc_id)
        if food is None:
            missing.append(ingredient.fdc_id)
            continue
        counted += 1
        for column in NUTRIENT_COLUMNS:
            per_100g = getattr(food, column)
            if per_100g is None:
                incomplete.setdefault(column, []).append(ingredient.fdc_id)
            else:
                total[column] += per_100g * ingredient.grams / 100

    total = {c: round(v, 2) for c, v in total.items()}
    per_serving = {c: round(v / servings, 2) for c, v in total.items()}
    return RecipeNutrition(found=counted > 0, servings=servings, per_serving=per_serving, total=total,
                           missing_fdc_ids=missing, incomplete_nutrients=incomplete)


# Keywords that reveal an allergen in an ingredient name.
ALLERGEN_KEYWORDS = {
    "peanuts": ["peanut", "groundnut"],
    "tree_nuts": ["almond", "walnut", "cashew", "pecan", "pistachio", "hazelnut", "macadamia", "pine nut",
                  "brazil nut", "chestnut", "coconut", "tree nut", "nut", "nut butter"],
    "shellfish": ["shrimp", "prawn", "crab", "lobster", "oyster", "clam", "mussel", "scallop", "squid", "crustacean", "mollusk"],
    "fish": ["fish", "salmon", "tuna", "cod", "tilapia", "sardine", "anchovy", "anchovies", "mackerel", "trout", "catfish"],
    "soy": ["soy", "soya", "soybean", "tofu", "tempeh", "miso", "edamame", "natto", "tamari", "shoyu"],
    "wheat_gluten": ["wheat", "flour", "bread", "pasta", "spaghetti", "noodle", "couscous", "bulgur", "semolina",
                     "seitan", "tortilla", "pita", "naan", "soy sauce", "barley", "rye", "cracker"],
    "eggs": ["egg", "mayonnaise", "mayo", "meringue"],
    "dairy": ["milk", "cheese", "butter", "cream", "yogurt", "yoghurt", "ghee", "paneer", "whey", "casein", "kefir"],
    "sesame": ["sesame", "tahini"],
}
# Words that make an ingredient's allergens unknowable from its name alone.
AMBIGUOUS_WORDS = ["sauce", "paste", "broth", "stock", "seasoning", "mix", "dressing", "noodle", "bar",
                   "spread", "marinade", "powder blend", "curry", "dumpling", "wrapper", "chips", "cereal", "dough"]
# Plain single foods with no top allergen (matched as whole words).
KNOWN_FREE_FOODS = [
    "rice", "onion", "garlic", "ginger", "carrot", "potato", "tomato", "cilantro", "parsley", "lime", "lemon",
    "apple", "banana", "spinach", "broccoli", "cabbage", "bok choy", "daikon", "radish", "lentil", "chickpea",
    "black bean", "pinto bean", "salt", "sugar", "honey", "water", "olive oil", "canola oil", "cumin",
    "turmeric", "black pepper", "paprika", "cinnamon", "cardamom", "chicken", "beef", "pork", "lamb",
    "cucumber", "zucchini", "eggplant", "mushroom", "avocado", "scallion", "green onion", "plantain", "cassava",
    "mango", "pineapple", "corn", "peas", "kale", "lettuce", "bell pepper", "jalapeno", "vinegar",
]


def _word_in(text: str, phrase: str) -> bool:
    """True if phrase appears as a whole word (or its plural): "nut" matches "nuts" but not "nutmeg"."""
    return re.search(rf"\b{re.escape(phrase)}(?:s|es)?\b", text) is not None


def check_allergens(ingredients: list[str | CatalogItem], allergens: list[str]) -> AllergenCheck:
    """Check ingredients against a person's allergens. Missing information is never reported as safe.

    Args:
        ingredients: Ingredient names (e.g. "soy sauce") or catalog items from search_catalog.
        allergens: Allergens to avoid, from: peanuts, tree_nuts, shellfish, fish, soy,
            wheat_gluten, eggs, dairy, sesame.

    A catalog item is judged by its allergen_tags. A plain name is judged by a keyword
    list: a keyword hit is a conflict; a name that is not clearly a plain allergen-free
    food (for example "curry paste" or an unknown product) goes to `uncertain`.
    all_clear is True only when there are no conflicts and nothing is uncertain.
    """
    wanted = [a.lower() for a in allergens]
    invalid = [a for a in wanted if a not in ALLERGENS]
    wanted = [a for a in wanted if a in ALLERGENS]

    conflicts: list[AllergenConflict] = []
    uncertain: list[UncertainIngredient] = []
    cleared: list[str] = []
    for ingredient in ingredients:
        if isinstance(ingredient, CatalogItem):
            name = ingredient.product_name
            hits = [a for a in wanted if a in ingredient.allergen_tags]
            conflicts += [AllergenConflict(ingredient=name, allergen=a, reason="listed in catalog allergen tags") for a in hits]
            if not hits:
                cleared.append(name)
            continue

        name = ingredient
        text = name.lower()
        hits = [a for a in wanted if any(_word_in(text, k) for k in ALLERGEN_KEYWORDS[a])]
        conflicts += [AllergenConflict(ingredient=name, allergen=a, reason="name contains an allergen keyword") for a in hits]
        if hits:
            continue
        if any(_word_in(text, w) for w in AMBIGUOUS_WORDS):
            uncertain.append(UncertainIngredient(ingredient=name, reason="processed food; allergens depend on the product label"))
        elif any(_word_in(text, f) for f in KNOWN_FREE_FOODS):
            cleared.append(name)
        else:
            uncertain.append(UncertainIngredient(ingredient=name, reason="not in the catalog or keyword list; check the label"))

    return AllergenCheck(
        conflicts=conflicts, uncertain=uncertain, cleared=cleared,
        all_clear=not conflicts and not uncertain and not invalid, invalid_allergens=invalid,
    )
