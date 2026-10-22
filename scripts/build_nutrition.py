"""Build data/nutrition.csv from USDA FoodData Central SR Legacy (public domain).

Run once: python scripts/build_nutrition.py
The resulting CSV is committed, so the app never downloads anything.
If the download is blocked, download the file below in a browser, save it as
scripts/sr_legacy.zip and run this script again.
"""

import csv
import io
import re
import shutil
import ssl
import urllib.request
import zipfile
from pathlib import Path

URL = "https://fdc.nal.usda.gov/fdc-datasets/FoodData_Central_sr_legacy_food_csv_2018-04.zip"
ZIP_PATH = Path(__file__).resolve().parent / "sr_legacy.zip"  # git-ignored download cache
OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "nutrition.csv"
MAX_ROWS = 3000

# USDA nutrient ids (per 100 g). Energy falls back to the Atwater ids if 1008 is missing.
NUTRIENTS = {
    "kcal": ["1008", "2047", "2048"],
    "protein_g": ["1003"],
    "fat_g": ["1004"],
    "carbs_g": ["1005"],
    "fiber_g": ["1079"],
    "sugar_g": ["2000"],
    "sodium_mg": ["1093"],
}
REQUIRED = ["kcal", "protein_g", "fat_g", "carbs_g"]  # rows missing these are dropped

# SR Legacy food categories we skip: baby foods, fast foods, branded cereals, packaged
# meals, American Indian/Alaska Native foods, restaurant foods.
SKIP_CATEGORIES = {"3", "21", "8", "22", "24", "25"}

# Description patterns that only add near-duplicate variants (cuts of meat by fat trim,
# salted copies, canned syrup packs, packaged sweets) and bloat the table.
SKIP_PATTERN = re.compile(
    r"trimmed to|Commodity|USDA|variety meats|prepared from|restaurant|fast food|"
    r", with salt|added solution|industrial|dry mix|Alcoholic|separable lean only|"
    r"separable fat|^Game meat|^Beverages|^Candies|^Pie fillings|^Puddings|"
    r"^Frozen novelty|frozen, unprepared|NFS|low calorie|fortified with|^Babyfood|"
    r"^Snacks|^Crackers|cookies?|Archway|Pillsbury|Kraft|Oscar Mayer|Nabisco|Mission Foods|Pepperidge|Hormel|Reddi|Martha White|Interstate|George Weston|Mckee|Continental Mills|Glutino|Schar|Udi|Van.s|Rudi|Andrea|Mary.s Gone|^Arrowhead|^Cake|^Pastry|^Waffle|^Pancakes|^Muffins|^Pie crust|"
    r"^Pies|syrup pack|juice pack|water pack|microwaved|with added ascorbic|"
    r"^Infant formula|^Sausage|^Frankfurter|^Bologna|^Salami|^Luncheon",
    re.IGNORECASE,
)

# Brand names are written in capitals (SILK, HORMEL, KRAFT); generic foods never are.
BRAND_PATTERN = re.compile(r"\b[A-Z]{3,}\b")
# USDA adds this note to some generic foods; drop the note, keep the food.
CLEAN_PATTERN = re.compile(r"\s*\(Includes foods for USDA's Food Distribution Program\)")

# Staples from East Asian, South Asian, Latin American, Middle Eastern and European
# cooking. Rows whose description matches are always kept, ahead of everything else.
STAPLES = re.compile(
    r"tofu|soy sauce|soybeans|miso|natto|tempeh|soy milk|cabbage, chinese|pak-choi|"
    r"radish, oriental|daikon|bamboo shoots|mushrooms, (shiitake|enoki|oyster|maitake)|"
    r"seaweed|noodles|rice|vermicelli|mung|lentils|chickpeas|garbanzo|pigeon peas|"
    r"cowpeas|black beans|pinto|kidney|tortillas|masa|corn flour|cornmeal|hominy|"
    r"plantain|cassava|taro|yam|jicama|tomatillo|chayote|avocado|chiles?|peppers|"
    r"cilantro|coriander|cumin|turmeric|ginger|garlic|curry|cardamom|cinnamon|"
    r"yogurt|cheese|butter oil|ghee|olive|sesame|tahini|coconut|bulgur|couscous|"
    r"pita|bread|pasta|spaghetti|macaroni|oats|barley|wheat flour|semolina|quinoa|"
    r"millet|buckwheat|fish sauce|oyster|shrimp|salmon|tuna|sardine|anchov|squid|"
    r"chicken|pork|beef|lamb|egg|milk|cream|onions|potatoes|carrots|tomato|spinach|"
    r"eggplant|zucchini|squash|cucumber|lemon|lime|vinegar|sugar|honey|salt|pepper|"
    r"peanut|almond|walnut|cashew|pistachio|raisins|dates|figs|apricot|"
    r"mustard|paprika|oregano|basil|parsley|dill|mint|thyme|rosemary|bay leaf|"
    r"saffron|fenugreek|tamarind|pomegranate|lard|oil,|banana|apples|oranges|grapes|"
    r"mango|papaya|pineapple|strawberr|blueberr|melon|oat|broccoli|cauliflower|kale|"
    r"collards|celery|lettuce|mushrooms|peas|beans|corn|pumpkin|cabbage|beets|leeks",
    re.IGNORECASE,
)


def download() -> zipfile.ZipFile:
    if not ZIP_PATH.exists():
        print("Downloading", URL)
        # certifi (installed with streamlit) supplies CA certificates; python.org builds on macOS lack them.
        import certifi

        context = ssl.create_default_context(cafile=certifi.where())
        with urllib.request.urlopen(URL, context=context) as response, ZIP_PATH.open("wb") as out:
            shutil.copyfileobj(response, out)
    return zipfile.ZipFile(ZIP_PATH)


def read_csv(z: zipfile.ZipFile, name: str):
    member = next(n for n in z.namelist() if n.endswith("/" + name))
    return csv.DictReader(io.TextIOWrapper(z.open(member), encoding="utf-8"))


def main() -> None:
    z = download()
    wanted = {nid for ids in NUTRIENTS.values() for nid in ids}

    amounts: dict[str, dict[str, str]] = {}
    for row in read_csv(z, "food_nutrient.csv"):
        if row["nutrient_id"] in wanted:
            amounts.setdefault(row["fdc_id"], {})[row["nutrient_id"]] = row["amount"]

    candidates = []
    for food in read_csv(z, "food.csv"):
        if food["food_category_id"] in SKIP_CATEGORIES:
            continue
        food["description"] = CLEAN_PATTERN.sub("", food["description"]).strip()
        if SKIP_PATTERN.search(food["description"]) or BRAND_PATTERN.search(food["description"]):
            continue
        have = amounts.get(food["fdc_id"], {})
        values = {}
        for column, ids in NUTRIENTS.items():
            values[column] = next((have[i] for i in ids if have.get(i)), "")
        if any(values[c] == "" for c in REQUIRED):
            continue
        candidates.append({"fdc_id": food["fdc_id"], "description": food["description"], **values})

    # Staples first, then the rest, simplest descriptions (fewest commas) first, up to MAX_ROWS.
    staples = [r for r in candidates if STAPLES.search(r["description"])]
    others = [r for r in candidates if not STAPLES.search(r["description"])]
    others.sort(key=lambda r: (r["description"].count(","), len(r["description"])))
    rows = (staples + others)[:MAX_ROWS]
    rows.sort(key=lambda r: r["description"])

    OUT_PATH.parent.mkdir(exist_ok=True)
    columns = ["fdc_id", "description", *NUTRIENTS]
    with OUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {OUT_PATH} ({len(staples)} staples, {len(candidates)} candidates)")


if __name__ == "__main__":
    main()
