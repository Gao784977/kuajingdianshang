"""Generate sample xlsx fixtures for V3.1 importer tests.

Run: python tests/fixtures/_generate_amazon_xlsx_fixtures.py

Creates 8 sample Excel files mimicking seller sprite / Brand Analytics exports:
- products.xlsx
- search.xlsx
- keyword_analysis.xlsx
- market_analysis.xlsx
- category_analysis.xlsx
- brand_analytics.xlsx
- brands.xlsx
- sellers.xlsx

Also creates variants for testing:
- products_english_headers.xlsx (English headers)
- products_chinese_headers.xlsx (Chinese headers)
- products_reordered_columns.xlsx (different column order)
- products_unknown_columns.xlsx (extra unknown columns)
- products_missing_optional.xlsx (optional fields missing)
- unknown_type.xlsx (unrecognizable file)
"""

from __future__ import annotations

from pathlib import Path

try:
    from openpyxl import Workbook
    from openpyxl.utils import get_column_letter
except ImportError:
    raise ImportError("openpyxl is required to generate fixtures")


FIXTURE_DIR = Path(__file__).parent


def _write_sheet(ws, headers: list[str], rows: list[list]) -> None:
    """Write headers + data rows to a worksheet."""
    for col_idx, header in enumerate(headers, 1):
        ws.cell(row=1, column=col_idx, value=header)
    for row_idx, row_data in enumerate(rows, 2):
        for col_idx, value in enumerate(row_data, 1):
            ws.cell(row=row_idx, column=col_idx, value=value)
    # Auto width
    for col_idx in range(1, len(headers) + 1):
        ws.column_dimensions[get_column_letter(col_idx)].width = 15


def make_products() -> None:
    """Products export with English headers."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Products"
    headers = [
        "ASIN", "SKU", "Parent ASIN", "Brand", "Brand Link", "Title",
        "Category Path", "Category", "Main Category", "Subcategory",
        "Main BSR", "Subcategory BSR", "Monthly Sales", "Monthly Revenue",
        "Price", "Prime Price", "Coupon", "Review Count", "Rating",
        "FBA Fee", "Margin Rate", "Launch Date", "Fulfillment Method",
        "Sellers Count", "Weight", "Dimensions",
    ]
    rows = [
        ["B0TEST001", "SKU-001", "B0PARENT001", "BrandA", "https://amazon.com/brandA",
         "Product Alpha One", "Pet Supplies > Poultry > Coop Door", "Poultry Habitat Supplies",
         "Pet Supplies", "Poultry", 1234, 56, 1500, 45000, 29.99, 27.99, 2.00,
         856, 4.2, 5.50, 0.35, "2025-01-15", "FBA", 3, 2.5, "30x20x10cm"],
        ["B0TEST002", "SKU-002", "B0PARENT002", "BrandB", "https://amazon.com/brandB",
         "Product Beta Two", "Pet Supplies > Poultry > Feeder", "Poultry Feeding Equipment",
         "Pet Supplies", "Poultry", 2345, 78, 3200, 76800, 23.99, 22.99, 0.00,
         1240, 4.5, 4.20, 0.40, "2024-11-20", "FBA", 5, 1.8, "25x15x8cm"],
        ["B0TEST003", "SKU-003", "", "BrandC", "", "Product Gamma Three",
         "Pet Supplies > Poultry > Waterer", "Poultry Watering Supplies",
         "Pet Supplies", "Poultry", 3456, 12, 800, 16000, 19.99, 19.49, 1.00,
         420, 3.8, 3.80, 0.25, "2025-03-01", "FBM", 1, 1.2, "20x12x6cm"],
    ]
    _write_sheet(ws, headers, rows)
    wb.save(FIXTURE_DIR / "products.xlsx")


def make_products_chinese() -> None:
    """Products export with Chinese headers."""
    wb = Workbook()
    ws = wb.active
    ws.title = "商品"
    headers = [
        "ASIN", "SKU", "父ASIN", "品牌", "品牌链接", "标题",
        "类目路径", "类目", "主类目", "子类目",
        "主BSR", "子类目BSR", "月销量", "月销售额($)",
        "价格", "Prime价格", "优惠券", "Review数量", "评分",
        "FBA费用", "毛利率", "上架日期", "配送方式",
        "卖家数", "重量", "尺寸",
    ]
    rows = [
        ["B0TEST001", "SKU-001", "B0PARENT001", "品牌A", "https://amazon.com/brandA",
         "产品甲", "宠物用品 > 家禽 > 鸡舍门", "家禽护理用品",
         "宠物用品", "家禽", 1234, 56, 1500, 45000, 29.99, 27.99, 2.00,
         856, 4.2, 5.50, 0.35, "2025-01-15", "FBA", 3, 2.5, "30x20x10cm"],
        ["B0TEST002", "SKU-002", "B0PARENT002", "品牌B", "https://amazon.com/brandB",
         "产品乙", "宠物用品 > 家禽 > 喂食器", "家禽喂食设备",
         "宠物用品", "家禽", 2345, 78, 3200, 76800, 23.99, 22.99, 0.00,
         1240, 4.5, 4.20, 0.40, "2024-11-20", "FBA", 5, 1.8, "25x15x8cm"],
    ]
    _write_sheet(ws, headers, rows)
    wb.save(FIXTURE_DIR / "products_chinese_headers.xlsx")


def make_products_reordered() -> None:
    """Products with columns in different order."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Products"
    # Reversed order + some missing
    headers = ["Rating", "Review Count", "Price", "Monthly Sales", "Brand", "Title", "ASIN"]
    rows = [
        [4.2, 856, 29.99, 1500, "BrandA", "Product Alpha One", "B0TEST001"],
        [4.5, 1240, 23.99, 3200, "BrandB", "Product Beta Two", "B0TEST002"],
    ]
    _write_sheet(ws, headers, rows)
    wb.save(FIXTURE_DIR / "products_reordered.xlsx")


def make_products_unknown_columns() -> None:
    """Products with extra unknown columns."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Products"
    headers = [
        "ASIN", "Brand", "Title", "Price", "Monthly Sales",
        "Review Count", "Rating", "Unknown Field X", "Custom Column Y",
    ]
    rows = [
        ["B0TEST001", "BrandA", "Product Alpha", 29.99, 1500, 856, 4.2, "data1", "data2"],
        ["B0TEST002", "BrandB", "Product Beta", 23.99, 3200, 1240, 4.5, "data3", "data4"],
    ]
    _write_sheet(ws, headers, rows)
    wb.save(FIXTURE_DIR / "products_unknown_columns.xlsx")


def make_products_missing_optional() -> None:
    """Products with required fields but missing optional ones."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Products"
    # Only required fields
    headers = ["ASIN", "Brand", "Title", "Price"]
    rows = [
        ["B0TEST001", "BrandA", "Product Alpha", 29.99],
        ["B0TEST002", "BrandB", "Product Beta", 23.99],
    ]
    _write_sheet(ws, headers, rows)
    wb.save(FIXTURE_DIR / "products_missing_optional.xlsx")


def make_search() -> None:
    """Search results export."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Search"
    headers = [
        "Keyword", "ASIN", "Search Rank", "Placement Type", "Placement Detail",
        "Is Sponsored", "Page Number", "Brand", "Title", "Price",
    ]
    rows = [
        ["chicken saddle", "B0TEST001", 1, "organic", "Page 1 Position 1", False, 1,
         "BrandA", "Product Alpha One", 29.99],
        ["chicken saddle", "B0TEST002", 2, "sponsored", "Page 1 Position 2", True, 1,
         "BrandB", "Product Beta Two", 23.99],
        ["chicken saddle", "B0TEST001", 3, "organic", "Page 1 Position 3", False, 1,
         "BrandA", "Product Alpha One", 29.99],
        ["chicken saddle", "B0TEST003", 4, "organic", "Page 1 Position 4", False, 1,
         "BrandC", "Product Gamma Three", 19.99],
        ["chicken coop", "B0TEST002", 1, "organic", "Page 1 Position 1", False, 1,
         "BrandB", "Product Beta Two", 23.99],
        ["chicken coop", "B0TEST001", 2, "sponsored", "Page 1 Position 2", True, 1,
         "BrandA", "Product Alpha One", 29.99],
    ]
    _write_sheet(ws, headers, rows)
    wb.save(FIXTURE_DIR / "search.xlsx")


def make_keyword_analysis() -> None:
    """Keyword analysis export."""
    wb = Workbook()
    ws = wb.active
    ws.title = "关键词分析"
    headers = [
        "Keyword", "Search Volume", "Search Growth", "Click Share",
        "Conversion Share", "Competition", "Related Keywords",
    ]
    rows = [
        ["chicken saddle", 12000, 0.05, 0.15, 0.08, "medium", "chicken diaper;chicken vest"],
        ["chicken coop accessories", 8500, 0.03, 0.12, 0.06, "low", "chicken coop door;chicken feeder"],
        ["poultry feeder", 5600, -0.02, 0.10, 0.05, "high", "chicken feeder; poultry waterer"],
    ]
    _write_sheet(ws, headers, rows)
    wb.save(FIXTURE_DIR / "keyword_analysis.xlsx")


def make_market_analysis() -> None:
    """Market analysis export."""
    wb = Workbook()
    ws = wb.active
    ws.title = "市场分析"
    headers = [
        "Category", "Category Path", "Product Count",
        "Market Sales", "Market Revenue", "Average Price",
        "Median Price", "Growth", "Competition",
    ]
    rows = [
        ["Poultry Habitat Supplies", "Pet Supplies > Poultry > Habitat", 156,
         450000, 13500000, 28.50, 27.99, 0.08, "medium"],
        ["Poultry Feeding Equipment", "Pet Supplies > Poultry > Feeding", 98,
         320000, 7680000, 24.00, 23.99, 0.05, "low"],
    ]
    _write_sheet(ws, headers, rows)
    wb.save(FIXTURE_DIR / "market_analysis.xlsx")


def make_category_analysis() -> None:
    """Category analysis export."""
    wb = Workbook()
    ws = wb.active
    ws.title = "类目分析"
    headers = [
        "Category", "Category Path", "Product Count",
        "Average Price", "Median Price", "Growth",
    ]
    rows = [
        ["Poultry Habitat Supplies", "Pet Supplies > Poultry > Habitat", 156, 28.50, 27.99, 0.08],
        ["Poultry Feeding Equipment", "Pet Supplies > Poultry > Feeding", 98, 24.00, 23.99, 0.05],
    ]
    _write_sheet(ws, headers, rows)
    wb.save(FIXTURE_DIR / "category_analysis.xlsx")


def make_brand_analytics() -> None:
    """Brand Analytics export."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Brand Analytics"
    headers = [
        "Brand", "Market Share", "Click Share", "Conversion Share",
        "Monthly Sales", "Monthly Revenue", "Average Price",
    ]
    rows = [
        ["BrandA", 0.25, 0.20, 0.15, 15000, 450000, 30.00],
        ["BrandB", 0.18, 0.15, 0.10, 10000, 240000, 24.00],
        ["BrandC", 0.10, 0.08, 0.05, 5000, 100000, 20.00],
    ]
    _write_sheet(ws, headers, rows)
    wb.save(FIXTURE_DIR / "brand_analytics.xlsx")


def make_brands() -> None:
    """Brands aggregate export."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Brands"
    headers = [
        "Brand", "Monthly Sales", "Monthly Revenue",
        "Annual Sales", "Annual Revenue", "Average Price", "Market Share",
    ]
    rows = [
        ["BrandA", 15000, 450000, 180000, 5400000, 30.00, 0.25],
        ["BrandB", 10000, 240000, 120000, 2880000, 24.00, 0.18],
        ["BrandC", 5000, 100000, 60000, 1200000, 20.00, 0.10],
    ]
    _write_sheet(ws, headers, rows)
    wb.save(FIXTURE_DIR / "brands.xlsx")


def make_sellers() -> None:
    """Sellers aggregate export."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Sellers"
    headers = [
        "Seller", "Monthly Sales", "Monthly Revenue",
        "Annual Sales", "Annual Revenue", "Average Price", "Market Share",
    ]
    rows = [
        ["SellerX", 20000, 600000, 240000, 7200000, 30.00, 0.30],
        ["SellerY", 12000, 288000, 144000, 3456000, 24.00, 0.15],
        ["SellerZ", 8000, 160000, 96000, 1920000, 20.00, 0.08],
    ]
    _write_sheet(ws, headers, rows)
    wb.save(FIXTURE_DIR / "sellers.xlsx")


def make_unknown() -> None:
    """Unrecognizable file for testing unknown detection."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Data"
    headers = ["Column1", "Column2", "Column3"]
    rows = [
        ["val1", "val2", "val3"],
        ["val4", "val5", "val6"],
    ]
    _write_sheet(ws, headers, rows)
    wb.save(FIXTURE_DIR / "unknown_type.xlsx")


def make_products_missing_required() -> None:
    """Products file missing required fields (no ASIN)."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Products"
    headers = ["Brand", "Title", "Price", "Monthly Sales"]
    rows = [
        ["BrandA", "Product Alpha", 29.99, 1500],
    ]
    _write_sheet(ws, headers, rows)
    wb.save(FIXTURE_DIR / "products_missing_required.xlsx")


def main() -> None:
    """Generate all fixture files."""
    print(f"Generating fixtures in {FIXTURE_DIR}")
    make_products()
    make_products_chinese()
    make_products_reordered()
    make_products_unknown_columns()
    make_products_missing_optional()
    make_products_missing_required()
    make_search()
    make_keyword_analysis()
    make_market_analysis()
    make_category_analysis()
    make_brand_analytics()
    make_brands()
    make_sellers()
    make_unknown()
    print(f"Generated {len(list(FIXTURE_DIR.glob('*.xlsx')))} xlsx fixtures")


if __name__ == "__main__":
    main()
