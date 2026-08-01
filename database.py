"""
Database layer — dual backend: Supabase (cloud) or SQLite (local).

Detection logic:
  1. Check environment variables SUPABASE_URL / SUPABASE_KEY
  2. Check .streamlit/secrets.toml
  3. If neither → fall back to local SQLite

All function signatures are preserved so app.py requires zero changes.
"""

import os
import json
import sqlite3
from datetime import date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "style_vault.db")

# ═══════════════════════════════════════════
#  Detect Backend
# ═══════════════════════════════════════════

SUPABASE_URL = None
SUPABASE_KEY = None

# Try env vars first (Streamlit Cloud / deployment)
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

# Try streamlit secrets (local development)
if not SUPABASE_URL or not SUPABASE_KEY:
    try:
        import streamlit as _st
        SUPABASE_URL = SUPABASE_URL or _st.secrets.get("SUPABASE_URL", "")
        SUPABASE_KEY = SUPABASE_KEY or _st.secrets.get("SUPABASE_KEY", "")
    except Exception:
        pass

USE_SUPABASE = bool(SUPABASE_URL and SUPABASE_KEY and "https://" in (SUPABASE_URL or ""))


# ═══════════════════════════════════════════
#  SQLite Backend (fallback)
# ═══════════════════════════════════════════

class _SQLite:
    def get_connection(self):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init_db(self):
        try:
            conn = self.get_connection()
            cur = conn.cursor()
            cur.execute("""CREATE TABLE IF NOT EXISTS clothes (
                id INTEGER PRIMARY KEY AUTOINCREMENT, image_path TEXT NOT NULL,
                name TEXT NOT NULL, category TEXT NOT NULL, material TEXT,
                color_hex TEXT, season TEXT, wear_count INTEGER DEFAULT 0,
                last_wear_date TEXT, is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now','localtime')))""")
            cur.execute("""CREATE TABLE IF NOT EXISTS accessories (
                id INTEGER PRIMARY KEY AUTOINCREMENT, image_path TEXT NOT NULL,
                name TEXT NOT NULL, part TEXT NOT NULL, material TEXT,
                color_hex TEXT, season TEXT,
                created_at TEXT DEFAULT (datetime('now','localtime')))""")
            cur.execute("""CREATE TABLE IF NOT EXISTS inspirations (
                id INTEGER PRIMARY KEY AUTOINCREMENT, image_path TEXT NOT NULL,
                title TEXT NOT NULL, type TEXT, tags TEXT DEFAULT '[]',
                extracted_colors TEXT DEFAULT '[]', pose_tags TEXT DEFAULT '[]',
                created_at TEXT DEFAULT (datetime('now','localtime')))""")
            for col in ["extracted_colors", "pose_tags"]:
                try: cur.execute(f"ALTER TABLE inspirations ADD COLUMN {col} TEXT DEFAULT '[]'")
                except sqlite3.OperationalError: pass
            cur.execute("""CREATE TABLE IF NOT EXISTS outfits (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
                scene TEXT, season TEXT, color_palette TEXT,
                outfit_date TEXT DEFAULT (date('now','localtime')),
                created_at TEXT DEFAULT (datetime('now','localtime')))""")
            cur.execute("""CREATE TABLE IF NOT EXISTS outfit_details (
                id INTEGER PRIMARY KEY AUTOINCREMENT, outfit_id INTEGER NOT NULL,
                item_type TEXT NOT NULL, item_id INTEGER NOT NULL,
                layer INTEGER DEFAULT 1,
                FOREIGN KEY (outfit_id) REFERENCES outfits(id) ON DELETE CASCADE)""")
            cur.execute("""CREATE TABLE IF NOT EXISTS wear_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT, clothes_id INTEGER NOT NULL,
                wear_date TEXT NOT NULL, temperature INTEGER, weather TEXT,
                scene TEXT, created_at TEXT DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (clothes_id) REFERENCES clothes(id) ON DELETE CASCADE)""")
            cur.execute("""CREATE TABLE IF NOT EXISTS user_settings (
                id INTEGER PRIMARY KEY, zodiac_sign TEXT, updated_at TIMESTAMP)""")
            conn.commit(); conn.close()
        except sqlite3.Error as e:
            raise RuntimeError(f"Database init failed: {e}") from e

    def _resolve_path(self, rel_path):
        if os.path.isabs(rel_path): return rel_path
        return os.path.join(BASE_DIR, rel_path)

    # ── Clothes ──
    def add_clothing(self, image_path, name, category, material="", color_hex="", season=""):
        conn = self.get_connection(); cur = conn.cursor()
        cur.execute("INSERT INTO clothes (image_path,name,category,material,color_hex,season) VALUES (?,?,?,?,?,?)",
                    (image_path, name, category, material, color_hex, season))
        conn.commit(); rid = cur.lastrowid; conn.close(); return rid

    def get_all_clothes(self, category="", material="", seasons=None, active_only=True):
        conn = self.get_connection(); cur = conn.cursor()
        sql = "SELECT * FROM clothes WHERE 1=1"; params = []
        if active_only: sql += " AND is_active = 1"
        if category: sql += " AND category = ?"; params.append(category)
        if material: sql += " AND material = ?"; params.append(material)
        sql += " ORDER BY created_at DESC"
        cur.execute(sql, params); rows = [dict(r) for r in cur.fetchall()]; conn.close()
        if seasons:
            filtered = []
            for r in rows:
                sv = r["season"] or ""
                try: item_seasons = json.loads(sv)
                except Exception: item_seasons = [sv] if sv else []
                if any(s in item_seasons for s in seasons): filtered.append(r)
            rows = filtered
        return rows

    def get_clothing_by_id(self, cid):
        conn = self.get_connection(); cur = conn.cursor()
        cur.execute("SELECT * FROM clothes WHERE id = ?", (cid,))
        row = cur.fetchone(); conn.close(); return dict(row) if row else None

    def increment_wear_count(self, cid):
        conn = self.get_connection(); cur = conn.cursor()
        cur.execute("UPDATE clothes SET wear_count=wear_count+1, last_wear_date=? WHERE id=?",
                    (date.today().isoformat(), cid)); conn.commit(); conn.close()

    def toggle_clothing_active(self, cid):
        conn = self.get_connection(); cur = conn.cursor()
        cur.execute("UPDATE clothes SET is_active=CASE WHEN is_active=1 THEN 0 ELSE 1 END WHERE id=?",
                    (cid,)); conn.commit(); conn.close()

    def delete_clothing(self, cid):
        conn = self.get_connection(); cur = conn.cursor()
        cur.execute("SELECT image_path FROM clothes WHERE id=?", (cid,))
        row = cur.fetchone()
        if row:
            ap = self._resolve_path(row["image_path"])
            if os.path.exists(ap):
                try: os.remove(ap)
                except OSError: pass
        cur.execute("DELETE FROM clothes WHERE id=?", (cid,)); conn.commit(); conn.close()

    def get_distinct_values(self, table, column):
        conn = self.get_connection(); cur = conn.cursor()
        cur.execute(f"SELECT DISTINCT {column} FROM {table} WHERE {column}!='' ORDER BY {column}")
        rows = [r[0] for r in cur.fetchall()]; conn.close(); return rows

    # ── Accessories ──
    def add_accessory(self, image_path, name, part, material="", color_hex="", season=""):
        conn = self.get_connection(); cur = conn.cursor()
        cur.execute("INSERT INTO accessories (image_path,name,part,material,color_hex,season) VALUES (?,?,?,?,?,?)",
                    (image_path, name, part, material, color_hex, season))
        conn.commit(); rid = cur.lastrowid; conn.close(); return rid

    def get_all_accessories(self):
        conn = self.get_connection(); cur = conn.cursor()
        cur.execute("SELECT * FROM accessories ORDER BY created_at DESC")
        rows = [dict(r) for r in cur.fetchall()]; conn.close(); return rows

    def delete_accessory(self, aid):
        conn = self.get_connection(); cur = conn.cursor()
        cur.execute("SELECT image_path FROM accessories WHERE id=?", (aid,))
        row = cur.fetchone()
        if row:
            ap = self._resolve_path(row["image_path"])
            if os.path.exists(ap):
                try: os.remove(ap)
                except OSError: pass
        cur.execute("DELETE FROM accessories WHERE id=?", (aid,)); conn.commit(); conn.close()

    # ── Inspirations ──
    def add_inspiration(self, image_path, title, insp_type="", tags="[]", pose_tags="[]"):
        conn = self.get_connection(); cur = conn.cursor()
        cur.execute("INSERT INTO inspirations (image_path,title,type,tags,pose_tags) VALUES (?,?,?,?,?)",
                    (image_path, title, insp_type, tags, pose_tags))
        conn.commit(); rid = cur.lastrowid; conn.close(); return rid

    def get_all_inspirations(self, insp_type=None, pose_tag=None):
        conn = self.get_connection(); cur = conn.cursor()
        sql = "SELECT * FROM inspirations WHERE 1=1"; params = []
        if insp_type: sql += " AND type = ?"; params.append(insp_type)
        if pose_tag:
            try:
                sql += " AND EXISTS (SELECT 1 FROM json_each(pose_tags) WHERE value = ?)"
                params.append(pose_tag)
                cur.execute(sql + " ORDER BY created_at DESC", params)
            except sqlite3.OperationalError:
                sql += " AND pose_tags LIKE ?"; params.append(f'%"{pose_tag}"%')
                cur.execute(sql + " ORDER BY created_at DESC", params)
        else:
            cur.execute(sql + " ORDER BY created_at DESC", params)
        rows = [dict(r) for r in cur.fetchall()]; conn.close(); return rows

    def get_inspiration_by_id(self, iid):
        conn = self.get_connection(); cur = conn.cursor()
        cur.execute("SELECT * FROM inspirations WHERE id=?", (iid,))
        row = cur.fetchone(); conn.close(); return dict(row) if row else None

    def delete_inspiration(self, iid):
        conn = self.get_connection(); cur = conn.cursor()
        cur.execute("SELECT image_path FROM inspirations WHERE id=?", (iid,))
        row = cur.fetchone()
        if row:
            ap = self._resolve_path(row["image_path"])
            if os.path.exists(ap):
                try: os.remove(ap)
                except OSError: pass
        cur.execute("DELETE FROM inspirations WHERE id=?", (iid,)); conn.commit(); conn.close()

    def update_inspiration_colors(self, iid, colors_json):
        conn = self.get_connection(); cur = conn.cursor()
        cur.execute("UPDATE inspirations SET extracted_colors=? WHERE id=?", (colors_json, iid))
        conn.commit(); conn.close()

    def get_distinct_pose_tags(self):
        conn = self.get_connection(); cur = conn.cursor()
        cur.execute("SELECT pose_tags FROM inspirations WHERE pose_tags!='[]' AND pose_tags!=''")
        all_tags = set()
        for row in cur.fetchall():
            try:
                for t in json.loads(row["pose_tags"]):
                    if t.strip(): all_tags.add(t.strip())
            except Exception: pass
        conn.close(); return sorted(all_tags)

    # ── Outfits ──
    def create_outfit(self, name, scene="", season="", color_palette=""):
        conn = self.get_connection(); cur = conn.cursor()
        cur.execute("INSERT INTO outfits (name,scene,season,color_palette) VALUES (?,?,?,?)",
                    (name, scene, season, color_palette))
        conn.commit(); rid = cur.lastrowid; conn.close(); return rid

    def add_outfit_detail(self, outfit_id, item_type, item_id, layer=1):
        conn = self.get_connection(); cur = conn.cursor()
        cur.execute("INSERT INTO outfit_details (outfit_id,item_type,item_id,layer) VALUES (?,?,?,?)",
                    (outfit_id, item_type, item_id, layer))
        conn.commit(); conn.close()

    def get_all_outfits(self):
        conn = self.get_connection(); cur = conn.cursor()
        cur.execute("SELECT * FROM outfits ORDER BY created_at DESC")
        rows = [dict(r) for r in cur.fetchall()]; conn.close(); return rows

    def get_outfit_details(self, outfit_id):
        conn = self.get_connection(); cur = conn.cursor()
        cur.execute("""SELECT od.id, od.outfit_id, od.item_type, od.item_id, od.layer,
            c.name AS item_name, c.image_path AS item_image, c.color_hex AS item_color,
            c.category AS item_category, c.material AS item_material
            FROM outfit_details od JOIN clothes c ON od.item_id=c.id AND od.item_type='clothes'
            WHERE od.outfit_id=?
            UNION ALL
            SELECT od.id, od.outfit_id, od.item_type, od.item_id, od.layer,
            a.name, a.image_path, a.color_hex, a.part, a.material
            FROM outfit_details od JOIN accessories a ON od.item_id=a.id AND od.item_type='accessories'
            WHERE od.outfit_id=? ORDER BY layer ASC""", (outfit_id, outfit_id))
        rows = [dict(r) for r in cur.fetchall()]; conn.close(); return rows

    def get_outfits_by_item(self, item_type, item_id):
        conn = self.get_connection(); cur = conn.cursor()
        cur.execute("""SELECT DISTINCT o.* FROM outfits o
            JOIN outfit_details od ON o.id=od.outfit_id
            WHERE od.item_type=? AND od.item_id=? ORDER BY o.created_at DESC""",
                    (item_type, item_id))
        rows = [dict(r) for r in cur.fetchall()]; conn.close(); return rows

    def delete_outfit(self, oid):
        conn = self.get_connection(); cur = conn.cursor()
        cur.execute("DELETE FROM outfits WHERE id=?", (oid,)); conn.commit(); conn.close()

    def remove_outfit_detail(self, did):
        conn = self.get_connection(); cur = conn.cursor()
        cur.execute("DELETE FROM outfit_details WHERE id=?", (did,)); conn.commit(); conn.close()

    def update_outfit_detail_layer(self, did, new_layer):
        conn = self.get_connection(); cur = conn.cursor()
        cur.execute("UPDATE outfit_details SET layer=? WHERE id=?", (new_layer, did))
        conn.commit(); conn.close()

    # ── Wear History ──
    def add_wear_history(self, clothes_id, wear_date, temperature=None, weather=None, scene=None):
        conn = self.get_connection(); cur = conn.cursor()
        cur.execute("INSERT INTO wear_history (clothes_id,wear_date,temperature,weather,scene) VALUES (?,?,?,?,?)",
                    (clothes_id, wear_date, temperature, weather, scene))
        conn.commit(); conn.close()

    def get_wear_history_count(self):
        conn = self.get_connection(); cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM wear_history")
        c = cur.fetchone()[0]; conn.close(); return c

    def get_fav_colors(self, limit=5):
        conn = self.get_connection(); cur = conn.cursor()
        cur.execute("""SELECT c.color_hex, COUNT(*) AS cnt FROM wear_history wh
            JOIN clothes c ON wh.clothes_id=c.id
            WHERE c.color_hex IS NOT NULL AND c.color_hex!='' AND c.color_hex!='#CCCCCC'
            GROUP BY c.color_hex ORDER BY cnt DESC LIMIT ?""", (limit,))
        rows = [dict(r) for r in cur.fetchall()]; conn.close(); return rows

    def get_fav_materials(self, limit=5):
        conn = self.get_connection(); cur = conn.cursor()
        cur.execute("""SELECT c.material, COUNT(*) AS cnt FROM wear_history wh
            JOIN clothes c ON wh.clothes_id=c.id
            WHERE c.material IS NOT NULL AND c.material!=''
            GROUP BY c.material ORDER BY cnt DESC LIMIT ?""", (limit,))
        rows = [dict(r) for r in cur.fetchall()]; conn.close(); return rows

    def get_fav_categories(self, limit=5):
        conn = self.get_connection(); cur = conn.cursor()
        cur.execute("""SELECT c.category, COUNT(*) AS cnt FROM wear_history wh
            JOIN clothes c ON wh.clothes_id=c.id
            WHERE c.category IS NOT NULL AND c.category!=''
            GROUP BY c.category ORDER BY cnt DESC LIMIT ?""", (limit,))
        rows = [dict(r) for r in cur.fetchall()]; conn.close(); return rows

    def get_most_worn_items(self, limit=10):
        conn = self.get_connection(); cur = conn.cursor()
        cur.execute("""SELECT c.id, c.name, c.category, c.color_hex, c.image_path,
            COUNT(wh.id) AS wear_times FROM wear_history wh
            JOIN clothes c ON wh.clothes_id=c.id
            GROUP BY c.id ORDER BY wear_times DESC LIMIT ?""", (limit,))
        rows = [dict(r) for r in cur.fetchall()]; conn.close(); return rows


# ═══════════════════════════════════════════
#  Supabase Backend
# ═══════════════════════════════════════════

class _Supabase:
    def __init__(self):
        from supabase import create_client
        self.client = create_client(SUPABASE_URL, SUPABASE_KEY)
        self._tables = {}

    def _t(self, name):
        """Get table reference."""
        if name not in self._tables:
            self._tables[name] = self.client.table(name)
        return self._tables[name]

    def _row(self, result):
        """Extract first row from Supabase response."""
        if result.data and len(result.data) > 0:
            return dict(result.data[0])
        return None

    def _rows(self, result):
        """Extract all rows."""
        return [dict(r) for r in (result.data or [])]

    def init_db(self):
        pass  # Tables must be created in Supabase dashboard

    # ── Clothes ──
    def add_clothing(self, image_path, name, category, material="", color_hex="", season=""):
        r = self._t("clothes").insert({
            "image_path": image_path, "name": name, "category": category,
            "material": material or "", "color_hex": color_hex or "",
            "season": season or "[]", "wear_count": 0, "is_active": True,
        }).execute()
        return r.data[0]["id"] if r.data else 0

    def get_all_clothes(self, category="", material="", seasons=None, active_only=True):
        q = self._t("clothes").select("*")
        if active_only: q = q.eq("is_active", True)
        if category: q = q.eq("category", category)
        if material: q = q.eq("material", material)
        q = q.order("created_at", desc=True)
        r = q.execute()
        rows = self._rows(r)

        # Python-side season filter (JSON array)
        if seasons and rows:
            filtered = []
            for row in rows:
                sv = row.get("season", "[]")
                if isinstance(sv, str):
                    try: sv = json.loads(sv)
                    except Exception: sv = [sv] if sv else []
                if isinstance(sv, list) and any(s in sv for s in seasons):
                    filtered.append(row)
            rows = filtered
        return rows

    def get_clothing_by_id(self, cid):
        r = self._t("clothes").select("*").eq("id", cid).execute()
        return self._row(r)

    def increment_wear_count(self, cid):
        item = self.get_clothing_by_id(cid)
        if item:
            self._t("clothes").update({
                "wear_count": (item.get("wear_count") or 0) + 1,
                "last_wear_date": date.today().isoformat(),
            }).eq("id", cid).execute()

    def toggle_clothing_active(self, cid):
        item = self.get_clothing_by_id(cid)
        if item:
            self._t("clothes").update({
                "is_active": not item.get("is_active", True)
            }).eq("id", cid).execute()

    def delete_clothing(self, cid):
        self._t("clothes").delete().eq("id", cid).execute()

    def get_distinct_values(self, table, column):
        r = self._t(table).select(column).neq(column, "").execute()
        vals = list({row.get(column, "") for row in (r.data or []) if row.get(column)})
        return sorted(vals)

    # ── Accessories ──
    def add_accessory(self, image_path, name, part, material="", color_hex="", season=""):
        r = self._t("accessories").insert({
            "image_path": image_path, "name": name, "part": part,
            "material": material or "", "color_hex": color_hex or "",
            "season": season or "[]",
        }).execute()
        return r.data[0]["id"] if r.data else 0

    def get_all_accessories(self):
        r = self._t("accessories").select("*").order("created_at", desc=True).execute()
        return self._rows(r)

    def delete_accessory(self, aid):
        self._t("accessories").delete().eq("id", aid).execute()

    # ── Inspirations ──
    def add_inspiration(self, image_path, title, insp_type="", tags="[]", pose_tags="[]"):
        r = self._t("inspirations").insert({
            "image_path": image_path, "title": title, "type": insp_type or "",
            "tags": tags, "pose_tags": pose_tags, "extracted_colors": "[]",
        }).execute()
        return r.data[0]["id"] if r.data else 0

    def get_all_inspirations(self, insp_type=None, pose_tag=None):
        q = self._t("inspirations").select("*")
        if insp_type: q = q.eq("type", insp_type)
        q = q.order("created_at", desc=True)
        r = q.execute()
        rows = self._rows(r)
        # Python-side pose_tag filter
        if pose_tag and rows:
            rows = [row for row in rows
                    if pose_tag in (json.loads(row.get("pose_tags", "[]"))
                                    if isinstance(row.get("pose_tags"), str)
                                    else row.get("pose_tags", []))]
        return rows

    def get_inspiration_by_id(self, iid):
        r = self._t("inspirations").select("*").eq("id", iid).execute()
        return self._row(r)

    def delete_inspiration(self, iid):
        self._t("inspirations").delete().eq("id", iid).execute()

    def update_inspiration_colors(self, iid, colors_json):
        self._t("inspirations").update({"extracted_colors": colors_json}).eq("id", iid).execute()

    def get_distinct_pose_tags(self):
        r = self._t("inspirations").select("pose_tags").neq("pose_tags", "[]").execute()
        all_tags = set()
        for row in (r.data or []):
            try:
                pt = json.loads(row.get("pose_tags", "[]")) if isinstance(row.get("pose_tags"), str) else row.get("pose_tags", [])
                for t in pt:
                    if t.strip(): all_tags.add(t.strip())
            except Exception: pass
        return sorted(all_tags)

    # ── Outfits ──
    def create_outfit(self, name, scene="", season="", color_palette=""):
        r = self._t("outfits").insert({
            "name": name, "scene": scene or "", "season": season or "",
            "color_palette": color_palette or "",
        }).execute()
        return r.data[0]["id"] if r.data else 0

    def add_outfit_detail(self, outfit_id, item_type, item_id, layer=1):
        self._t("outfit_details").insert({
            "outfit_id": outfit_id, "item_type": item_type,
            "item_id": item_id, "layer": layer,
        }).execute()

    def get_all_outfits(self):
        r = self._t("outfits").select("*").order("created_at", desc=True).execute()
        return self._rows(r)

    def get_outfit_details(self, outfit_id):
        # Supabase can't do UNION, so fetch separately and merge
        r1 = self._t("outfit_details").select("*, clothes!inner(name, image_path, color_hex, category, material)") \
            .eq("outfit_id", outfit_id).eq("item_type", "clothes").execute()
        r2 = self._t("outfit_details").select("*, accessories!inner(name, image_path, color_hex, part, material)") \
            .eq("outfit_id", outfit_id).eq("item_type", "accessories").execute()
        rows = []
        for r in (r1.data or []):
            c = r.get("clothes", {}) or {}
            rows.append({
                "id": r["id"], "outfit_id": r["outfit_id"], "item_type": r["item_type"],
                "item_id": r["item_id"], "layer": r.get("layer", 1),
                "item_name": c.get("name", ""), "item_image": c.get("image_path", ""),
                "item_color": c.get("color_hex", ""), "item_category": c.get("category", ""),
                "item_material": c.get("material", ""),
            })
        for r in (r2.data or []):
            a = r.get("accessories", {}) or {}
            rows.append({
                "id": r["id"], "outfit_id": r["outfit_id"], "item_type": r["item_type"],
                "item_id": r["item_id"], "layer": r.get("layer", 1),
                "item_name": a.get("name", ""), "item_image": a.get("image_path", ""),
                "item_color": a.get("color_hex", ""), "item_category": a.get("part", ""),
                "item_material": a.get("material", ""),
            })
        rows.sort(key=lambda x: x.get("layer", 1))
        return rows

    def get_outfits_by_item(self, item_type, item_id):
        r = self._t("outfit_details").select("outfit_id") \
            .eq("item_type", item_type).eq("item_id", item_id).execute()
        oids = list({row["outfit_id"] for row in (r.data or [])})
        if not oids: return []
        result = []
        for oid in oids:
            rr = self._t("outfits").select("*").eq("id", oid).execute()
            if rr.data: result.extend(self._rows(rr))
        return result

    def delete_outfit(self, oid):
        self._t("outfits").delete().eq("id", oid).execute()

    def remove_outfit_detail(self, did):
        self._t("outfit_details").delete().eq("id", did).execute()

    def update_outfit_detail_layer(self, did, new_layer):
        self._t("outfit_details").update({"layer": new_layer}).eq("id", did).execute()

    # ── Wear History ──
    def add_wear_history(self, clothes_id, wear_date, temperature=None, weather=None, scene=None):
        self._t("wear_history").insert({
            "clothes_id": clothes_id, "wear_date": wear_date,
            "temperature": temperature, "weather": weather or "", "scene": scene or "",
        }).execute()

    def get_wear_history_count(self):
        r = self._t("wear_history").select("id", count="exact").execute()
        return r.count or 0

    def get_fav_colors(self, limit=5):
        r = self._t("wear_history").select("clothes_id, clothes(color_hex)").execute()
        counts = {}
        for row in (r.data or []):
            c = row.get("clothes", {}) or {}
            h = c.get("color_hex", "")
            if h and h != "#CCCCCC":
                counts[h] = counts.get(h, 0) + 1
        return [{"color_hex": k, "cnt": v} for k, v in
                sorted(counts.items(), key=lambda x: -x[1])[:limit]]

    def get_fav_materials(self, limit=5):
        r = self._t("wear_history").select("clothes_id, clothes(material)").execute()
        counts = {}
        for row in (r.data or []):
            m = (row.get("clothes", {}) or {}).get("material", "")
            if m: counts[m] = counts.get(m, 0) + 1
        return [{"material": k, "cnt": v} for k, v in
                sorted(counts.items(), key=lambda x: -x[1])[:limit]]

    def get_fav_categories(self, limit=5):
        r = self._t("wear_history").select("clothes_id, clothes(category)").execute()
        counts = {}
        for row in (r.data or []):
            c = (row.get("clothes", {}) or {}).get("category", "")
            if c: counts[c] = counts.get(c, 0) + 1
        return [{"category": k, "cnt": v} for k, v in
                sorted(counts.items(), key=lambda x: -x[1])[:limit]]

    def get_most_worn_items(self, limit=10):
        r = self._t("wear_history").select("clothes_id, clothes(id, name, category, color_hex, image_path)").execute()
        counts = {}
        details = {}
        for row in (r.data or []):
            cid = row["clothes_id"]
            counts[cid] = counts.get(cid, 0) + 1
            if cid not in details:
                details[cid] = row.get("clothes", {}) or {}
        items = []
        for cid, cnt in sorted(counts.items(), key=lambda x: -x[1])[:limit]:
            d = details.get(cid, {})
            items.append({"id": cid, "wear_times": cnt, **d})
        return items


# ═══════════════════════════════════════════
#  Instantiate Backend
# ═══════════════════════════════════════════

if USE_SUPABASE:
    _backend = _Supabase()
else:
    _backend = _SQLite()


# ═══════════════════════════════════════════
#  Module-level exports (delegate to backend)
# ═══════════════════════════════════════════

get_connection      = _backend.get_connection if hasattr(_backend, "get_connection") else (lambda: None)
init_db             = _backend.init_db
add_clothing        = _backend.add_clothing
get_all_clothes     = _backend.get_all_clothes
get_clothing_by_id  = _backend.get_clothing_by_id
increment_wear_count = _backend.increment_wear_count
toggle_clothing_active = _backend.toggle_clothing_active
delete_clothing     = _backend.delete_clothing
get_distinct_values = _backend.get_distinct_values
add_accessory       = _backend.add_accessory
get_all_accessories = _backend.get_all_accessories
delete_accessory    = _backend.delete_accessory
add_inspiration     = _backend.add_inspiration
get_all_inspirations = _backend.get_all_inspirations
get_inspiration_by_id = _backend.get_inspiration_by_id
delete_inspiration  = _backend.delete_inspiration
update_inspiration_colors = _backend.update_inspiration_colors
get_distinct_pose_tags = _backend.get_distinct_pose_tags
create_outfit       = _backend.create_outfit
add_outfit_detail   = _backend.add_outfit_detail
get_all_outfits     = _backend.get_all_outfits
get_outfit_details  = _backend.get_outfit_details
get_outfits_by_item = _backend.get_outfits_by_item
delete_outfit       = _backend.delete_outfit
remove_outfit_detail = _backend.remove_outfit_detail
update_outfit_detail_layer = _backend.update_outfit_detail_layer
add_wear_history    = _backend.add_wear_history
get_wear_history_count = _backend.get_wear_history_count
get_fav_colors      = _backend.get_fav_colors
get_fav_materials   = _backend.get_fav_materials
get_fav_categories  = _backend.get_fav_categories
get_most_worn_items = _backend.get_most_worn_items
