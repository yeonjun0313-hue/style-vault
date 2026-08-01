"""
SQLite database operations -- create tables, CRUD.

Database design:
- clothes: wardrobe items with color/material/season tracking
- accessories: jewelry/accessories grouped by body part
- inspirations: mood board images with tags and extracted colors
- outfits: outfit plans with scene/season/palette
- outfit_details: many-to-many link between outfits and items
"""

import sqlite3
import json
import os
from datetime import date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "style_vault.db")


def get_connection() -> sqlite3.Connection:
    """Get database connection with Row factory for dict-like access."""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn
    except sqlite3.Error as e:
        raise RuntimeError(f"Cannot connect to database ({DB_PATH}): {e}") from e


def init_db():
    """Initialize all tables (idempotent via IF NOT EXISTS)."""
    try:
        conn = get_connection()
        cur = conn.cursor()

        # --- clothes ---
        cur.execute("""
            CREATE TABLE IF NOT EXISTS clothes (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                image_path      TEXT    NOT NULL,
                name            TEXT    NOT NULL,
                category        TEXT    NOT NULL,
                material        TEXT,
                color_hex       TEXT,
                season          TEXT,
                wear_count      INTEGER DEFAULT 0,
                last_wear_date  TEXT,
                is_active       INTEGER DEFAULT 1,
                created_at      TEXT    DEFAULT (datetime('now','localtime'))
            )
        """)

        # --- accessories ---
        cur.execute("""
            CREATE TABLE IF NOT EXISTS accessories (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                image_path      TEXT    NOT NULL,
                name            TEXT    NOT NULL,
                part            TEXT    NOT NULL,
                material        TEXT,
                color_hex       TEXT,
                season          TEXT,
                created_at      TEXT    DEFAULT (datetime('now','localtime'))
            )
        """)

        # --- inspirations ---
        cur.execute("""
            CREATE TABLE IF NOT EXISTS inspirations (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                image_path       TEXT    NOT NULL,
                title            TEXT    NOT NULL,
                type             TEXT,
                tags             TEXT    DEFAULT '[]',
                extracted_colors TEXT    DEFAULT '[]',
                pose_tags        TEXT    DEFAULT '[]',
                created_at       TEXT    DEFAULT (datetime('now','localtime'))
            )
        """)

        # Migrate: add columns if missing (old DB compat)
        for col_name in ["extracted_colors", "pose_tags"]:
            try:
                cur.execute(
                    f"ALTER TABLE inspirations ADD COLUMN {col_name} TEXT DEFAULT '[]'"
                )
            except sqlite3.OperationalError:
                pass

        # --- outfits ---
        cur.execute("""
            CREATE TABLE IF NOT EXISTS outfits (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                name            TEXT    NOT NULL,
                scene           TEXT,
                season          TEXT,
                color_palette   TEXT,
                outfit_date     TEXT    DEFAULT (date('now','localtime')),
                created_at      TEXT    DEFAULT (datetime('now','localtime'))
            )
        """)

        # --- outfit_details (many-to-many link) ---
        cur.execute("""
            CREATE TABLE IF NOT EXISTS outfit_details (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                outfit_id       INTEGER NOT NULL,
                item_type       TEXT    NOT NULL,
                item_id         INTEGER NOT NULL,
                layer           INTEGER DEFAULT 1,
                FOREIGN KEY (outfit_id) REFERENCES outfits(id) ON DELETE CASCADE
            )
        """)

        # --- wear_history ---
        cur.execute("""
            CREATE TABLE IF NOT EXISTS wear_history (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                clothes_id      INTEGER NOT NULL,
                wear_date       TEXT    NOT NULL,
                temperature     INTEGER,
                weather         TEXT,
                scene           TEXT,
                created_at      TEXT    DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (clothes_id) REFERENCES clothes(id) ON DELETE CASCADE
            )
        """)

        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        raise RuntimeError(f"Database initialization failed: {e}") from e


# ============================================================
#  Utility
# ============================================================

def _resolve_image_path(rel_path: str) -> str:
    """Convert DB relative path to absolute path for file deletion."""
    if os.path.isabs(rel_path):
        return rel_path
    return os.path.join(BASE_DIR, rel_path)


# ============================================================
#  Clothes CRUD
# ============================================================

def add_clothing(image_path: str, name: str, category: str,
                 material: str = "", color_hex: str = "", season: str = "") -> int:
    """Insert a clothing item. Returns new row ID."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO clothes (image_path, name, category, material, color_hex, season) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (image_path, name, category, material, color_hex, season),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id
    except sqlite3.Error as e:
        raise RuntimeError(f"Failed to add clothing ({name}): {e}") from e


def get_all_clothes(category: str = "", material: str = "",
                    seasons: list = None, active_only: bool = True) -> list[dict]:
    """
    Query clothes with optional filters.

    Filter logic (AND concatenation):
    - active_only=True -> WHERE is_active = 1
    - category non-empty -> AND category = ?
    - material non-empty -> AND material = ?
    - seasons non-empty   -> AND season IN (?,?,...)

    All parameters use parameterized queries to prevent SQL injection.
    """
    try:
        conn = get_connection()
        cur = conn.cursor()

        sql = "SELECT * FROM clothes WHERE 1=1"
        params = []

        if active_only:
            sql += " AND is_active = 1"
        if category:
            sql += " AND category = ?"
            params.append(category)
        if material:
            sql += " AND material = ?"
            params.append(material)
        # Season filter is applied in Python because season is stored as
        # a JSON array (multi-select). We skip SQL filtering for season
        # and do it after fetching all matched rows.
        sql += " ORDER BY created_at DESC"
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()

        # Python-side season filter (handles both JSON arrays and legacy strings)
        if seasons:
            filtered = []
            for r in rows:
                sv = r["season"]
                if not sv:
                    continue
                # Parse season value: try JSON array first, fall back to single string
                try:
                    item_seasons = json.loads(sv)
                except (json.JSONDecodeError, TypeError):
                    item_seasons = [sv] if sv else []
                # Check if any requested season matches
                if any(s in item_seasons for s in seasons):
                    filtered.append(r)
            rows = filtered

        return rows
    except sqlite3.Error as e:
        raise RuntimeError(f"Failed to query clothes: {e}") from e


def get_clothing_by_id(clothing_id: int) -> dict | None:
    """Get a single clothing item by ID."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM clothes WHERE id = ?", (clothing_id,))
        row = cur.fetchone()
        conn.close()
        return dict(row) if row else None
    except sqlite3.Error as e:
        raise RuntimeError(f"Failed to get clothing (ID={clothing_id}): {e}") from e


def increment_wear_count(clothing_id: int):
    """wear_count += 1, update last_wear_date to today."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        today = date.today().isoformat()
        cur.execute(
            "UPDATE clothes SET wear_count = wear_count + 1, last_wear_date = ? WHERE id = ?",
            (today, clothing_id),
        )
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        raise RuntimeError(f"Failed to update wear count (ID={clothing_id}): {e}") from e


def toggle_clothing_active(clothing_id: int):
    """Flip is_active flag (atomic toggle via CASE WHEN)."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE clothes SET is_active = CASE WHEN is_active = 1 THEN 0 ELSE 1 END "
            "WHERE id = ?",
            (clothing_id,),
        )
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        raise RuntimeError(f"Failed to toggle clothing (ID={clothing_id}): {e}") from e


def delete_clothing(clothing_id: int):
    """Hard-delete clothing record and its image file."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT image_path FROM clothes WHERE id = ?", (clothing_id,))
        row = cur.fetchone()

        if row:
            abs_path = _resolve_image_path(row["image_path"])
            try:
                if os.path.exists(abs_path):
                    os.remove(abs_path)
            except OSError as e:
                print(f"[File deletion failed] {abs_path}: {e}")

        cur.execute("DELETE FROM clothes WHERE id = ?", (clothing_id,))
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        raise RuntimeError(f"Failed to delete clothing (ID={clothing_id}): {e}") from e


def get_distinct_values(table: str, column: str) -> list[str]:
    """Get distinct non-empty values for a column (used for filter dropdowns)."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            f"SELECT DISTINCT {column} FROM {table} WHERE {column} != '' ORDER BY {column}"
        )
        rows = [r[0] for r in cur.fetchall()]
        conn.close()
        return rows
    except sqlite3.Error as e:
        raise RuntimeError(f"Failed to get distinct values ({table}.{column}): {e}") from e


# ============================================================
#  Accessories CRUD
# ============================================================

def add_accessory(image_path: str, name: str, part: str,
                  material: str = "", color_hex: str = "", season: str = "") -> int:
    """Insert an accessory. Returns new row ID."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO accessories (image_path, name, part, material, color_hex, season) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (image_path, name, part, material, color_hex, season),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id
    except sqlite3.Error as e:
        raise RuntimeError(f"Failed to add accessory ({name}): {e}") from e


def get_all_accessories() -> list[dict]:
    """Get all accessories, ordered by creation time DESC."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM accessories ORDER BY created_at DESC")
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows
    except sqlite3.Error as e:
        raise RuntimeError(f"Failed to query accessories: {e}") from e


def delete_accessory(acc_id: int):
    """Delete accessory record and its image file."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT image_path FROM accessories WHERE id = ?", (acc_id,))
        row = cur.fetchone()

        if row:
            abs_path = _resolve_image_path(row["image_path"])
            try:
                if os.path.exists(abs_path):
                    os.remove(abs_path)
            except OSError as e:
                print(f"[File deletion failed] {abs_path}: {e}")

        cur.execute("DELETE FROM accessories WHERE id = ?", (acc_id,))
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        raise RuntimeError(f"Failed to delete accessory (ID={acc_id}): {e}") from e


# ============================================================
#  Inspirations CRUD
# ============================================================

def add_inspiration(image_path: str, title: str, insp_type: str = "",
                    tags: str = "[]", pose_tags: str = "[]") -> int:
    """Insert an inspiration image. Tags and pose_tags are JSON array strings."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO inspirations (image_path, title, type, tags, pose_tags) "
            "VALUES (?, ?, ?, ?, ?)",
            (image_path, title, insp_type, tags, pose_tags),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id
    except sqlite3.Error as e:
        raise RuntimeError(f"Failed to add inspiration ({title}): {e}") from e


def get_all_inspirations(insp_type=None, pose_tag=None) -> list[dict]:
    """
    Get all inspirations, optionally filtered by type and/or pose tag.

    pose_tag filtering uses json_each() to match values in the JSON array field.
    Falls back to LIKE matching if json_each is not available (older SQLite).
    """
    try:
        conn = get_connection()
        cur = conn.cursor()

        sql = "SELECT * FROM inspirations WHERE 1=1"
        params = []

        if insp_type:
            sql += " AND type = ?"
            params.append(insp_type)

        if pose_tag:
            # Try json_each first (standard SQLite JSON extension)
            # Fall back to LIKE matching if json_each fails
            try:
                sql += " AND EXISTS (SELECT 1 FROM json_each(pose_tags) WHERE value = ?)"
                params.append(pose_tag)
                cur.execute(sql + " ORDER BY created_at DESC", params)
            except sqlite3.OperationalError:
                # json_each not available, use LIKE as fallback
                sql += " AND pose_tags LIKE ?"
                params.append(f'%"{pose_tag}"%')
                cur.execute(sql + " ORDER BY created_at DESC", params)
        else:
            cur.execute(sql + " ORDER BY created_at DESC", params)

        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows
    except sqlite3.Error as e:
        raise RuntimeError(f"Failed to query inspirations: {e}") from e


def get_distinct_pose_tags() -> list[str]:
    """
    Get all unique pose tags across all inspirations.
    Parses JSON arrays and returns distinct tag values for filter dropdown.
    """
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT pose_tags FROM inspirations WHERE pose_tags != '[]' AND pose_tags != ''")
        all_tags = set()
        for row in cur.fetchall():
            try:
                tags = json.loads(row["pose_tags"])
                for t in tags:
                    if t.strip():
                        all_tags.add(t.strip())
            except (json.JSONDecodeError, TypeError):
                pass
        conn.close()
        return sorted(all_tags)
    except sqlite3.Error as e:
        raise RuntimeError(f"Failed to get pose tags: {e}") from e


def get_existing_colors() -> list[str]:
    """Get all distinct non-empty color_hex values from the clothes table."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT DISTINCT color_hex FROM clothes "
            "WHERE color_hex IS NOT NULL AND color_hex != '' "
            "AND is_active = 1 ORDER BY color_hex"
        )
        rows = [r[0] for r in cur.fetchall()]
        conn.close()
        return rows
    except sqlite3.Error as e:
        raise RuntimeError(f"Failed to get existing colors: {e}") from e


def get_inspiration_by_id(insp_id: int) -> dict | None:
    """Get a single inspiration by ID."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM inspirations WHERE id = ?", (insp_id,))
        row = cur.fetchone()
        conn.close()
        return dict(row) if row else None
    except sqlite3.Error as e:
        raise RuntimeError(f"Failed to get inspiration (ID={insp_id}): {e}") from e


def delete_inspiration(insp_id: int):
    """Delete inspiration record and its image file."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT image_path FROM inspirations WHERE id = ?", (insp_id,))
        row = cur.fetchone()

        if row:
            abs_path = _resolve_image_path(row["image_path"])
            try:
                if os.path.exists(abs_path):
                    os.remove(abs_path)
            except OSError as e:
                print(f"[File deletion failed] {abs_path}: {e}")

        cur.execute("DELETE FROM inspirations WHERE id = ?", (insp_id,))
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        raise RuntimeError(f"Failed to delete inspiration (ID={insp_id}): {e}") from e


def update_inspiration_colors(insp_id: int, colors_json: str):
    """Update the extracted_colors field for an inspiration."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE inspirations SET extracted_colors = ? WHERE id = ?",
            (colors_json, insp_id),
        )
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        raise RuntimeError(f"Failed to update inspiration colors (ID={insp_id}): {e}") from e


# ============================================================
#  Outfits CRUD
# ============================================================

def create_outfit(name: str, scene: str = "", season: str = "",
                  color_palette: str = "") -> int:
    """Create a new outfit plan. Returns outfit ID."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO outfits (name, scene, season, color_palette) VALUES (?, ?, ?, ?)",
            (name, scene, season, color_palette),
        )
        conn.commit()
        outfit_id = cur.lastrowid
        conn.close()
        return outfit_id
    except sqlite3.Error as e:
        raise RuntimeError(f"Failed to create outfit ({name}): {e}") from e


def add_outfit_detail(outfit_id: int, item_type: str, item_id: int,
                      layer: int = 1):
    """Add an item (clothes/accessory) to an outfit plan."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO outfit_details (outfit_id, item_type, item_id, layer) "
            "VALUES (?, ?, ?, ?)",
            (outfit_id, item_type, item_id, layer),
        )
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        raise RuntimeError(f"Failed to add outfit detail: {e}") from e


def get_all_outfits() -> list[dict]:
    """Get all outfits, ordered by creation time DESC."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM outfits ORDER BY created_at DESC")
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows
    except sqlite3.Error as e:
        raise RuntimeError(f"Failed to query outfits: {e}") from e


def get_outfit_details(outfit_id: int) -> list[dict]:
    """
    Get all items in an outfit with their full details.

    Uses UNION ALL to join outfit_details with both clothes and accessories tables,
    returning a unified result set ordered by layer ASC (inner -> outer -> accessories).
    """
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT
                od.id, od.outfit_id, od.item_type, od.item_id, od.layer,
                c.name AS item_name,
                c.image_path AS item_image,
                c.color_hex AS item_color,
                c.category AS item_category,
                c.material AS item_material
            FROM outfit_details od
            JOIN clothes c ON od.item_id = c.id AND od.item_type = 'clothes'
            WHERE od.outfit_id = ?

            UNION ALL

            SELECT
                od.id, od.outfit_id, od.item_type, od.item_id, od.layer,
                a.name AS item_name,
                a.image_path AS item_image,
                a.color_hex AS item_color,
                a.part AS item_category,
                a.material AS item_material
            FROM outfit_details od
            JOIN accessories a ON od.item_id = a.id AND od.item_type = 'accessories'
            WHERE od.outfit_id = ?

            ORDER BY layer ASC
        """, (outfit_id, outfit_id))

        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows
    except sqlite3.Error as e:
        raise RuntimeError(f"Failed to get outfit details (ID={outfit_id}): {e}") from e


def get_outfits_by_item(item_type: str, item_id: int) -> list[dict]:
    """
    [One-piece-many-ways] Find all outfits that contain a specific item.

    Searches outfit_details for matching item_type + item_id,
    then JOINs with outfits to return outfit metadata.
    """
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT DISTINCT o.*
            FROM outfits o
            JOIN outfit_details od ON o.id = od.outfit_id
            WHERE od.item_type = ? AND od.item_id = ?
            ORDER BY o.created_at DESC
        """, (item_type, item_id))
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows
    except sqlite3.Error as e:
        raise RuntimeError(f"Failed to query outfits by item: {e}") from e


def delete_outfit(outfit_id: int):
    """
    Delete an outfit and all its details.
    ON DELETE CASCADE on outfit_details handles the cleanup automatically.
    """
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM outfits WHERE id = ?", (outfit_id,))
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        raise RuntimeError(f"Failed to delete outfit (ID={outfit_id}): {e}") from e


def remove_outfit_detail(detail_id: int):
    """Remove a single item from an outfit."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM outfit_details WHERE id = ?", (detail_id,))
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        raise RuntimeError(f"Failed to remove outfit detail: {e}") from e


def update_outfit_detail_layer(detail_id: int, new_layer: int):
    """Update the layer (sort order) of an outfit detail."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE outfit_details SET layer = ? WHERE id = ?",
            (new_layer, detail_id),
        )
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        raise RuntimeError(f"Failed to update layer: {e}") from e


# ============================================================
#  Wear History & Preferences
# ============================================================

def add_wear_history(clothes_id, wear_date, temperature=None, weather=None, scene=None):
    """Log a wear event."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO wear_history (clothes_id, wear_date, temperature, weather, scene) "
            "VALUES (?, ?, ?, ?, ?)",
            (clothes_id, wear_date, temperature, weather, scene),
        )
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        raise RuntimeError(f"Failed to log wear history: {e}") from e


def get_wear_history_count() -> int:
    """Total number of wear history records."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM wear_history")
        count = cur.fetchone()[0]
        conn.close()
        return count
    except sqlite3.Error:
        return 0


def get_fav_colors(limit=5) -> list[dict]:
    """Top N most-worn colors."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT c.color_hex, COUNT(*) AS cnt
            FROM wear_history wh
            JOIN clothes c ON wh.clothes_id = c.id
            WHERE c.color_hex IS NOT NULL AND c.color_hex != '' AND c.color_hex != '#CCCCCC'
            GROUP BY c.color_hex
            ORDER BY cnt DESC LIMIT ?
        """, (limit,))
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows
    except sqlite3.Error:
        return []


def get_fav_materials(limit=5) -> list[dict]:
    """Top N most-worn materials."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT c.material, COUNT(*) AS cnt
            FROM wear_history wh
            JOIN clothes c ON wh.clothes_id = c.id
            WHERE c.material IS NOT NULL AND c.material != ''
            GROUP BY c.material
            ORDER BY cnt DESC LIMIT ?
        """, (limit,))
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows
    except sqlite3.Error:
        return []


def get_fav_categories(limit=5) -> list[dict]:
    """Top N most-worn categories."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT c.category, COUNT(*) AS cnt
            FROM wear_history wh
            JOIN clothes c ON wh.clothes_id = c.id
            WHERE c.category IS NOT NULL AND c.category != ''
            GROUP BY c.category
            ORDER BY cnt DESC LIMIT ?
        """, (limit,))
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows
    except sqlite3.Error:
        return []


def get_wear_by_date() -> list[dict]:
    """Wear counts by date (for calendar heatmap)."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT wear_date, COUNT(*) AS cnt
            FROM wear_history
            WHERE wear_date >= date('now', '-30 days')
            GROUP BY wear_date ORDER BY wear_date
        """)
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows
    except sqlite3.Error:
        return []


def get_most_worn_items(limit=10) -> list[dict]:
    """Most frequently worn individual items."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT c.id, c.name, c.category, c.color_hex, c.image_path,
                   COUNT(wh.id) AS wear_times
            FROM wear_history wh
            JOIN clothes c ON wh.clothes_id = c.id
            GROUP BY c.id
            ORDER BY wear_times DESC LIMIT ?
        """, (limit,))
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows
    except sqlite3.Error:
        return []
