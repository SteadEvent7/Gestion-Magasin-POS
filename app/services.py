from __future__ import annotations

import json
import re
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl
from urllib.request import urlopen
from urllib.error import URLError

from .config import APP_PATCH, APP_UPDATE_URL, APP_VERSION, BACKUPS_DIR
from .db import column_exists, execute, fetch_all, fetch_one, get_connection, is_sqlite
from .security import hash_password, verify_password


class StoreService:
    def _parse_version(self, version: str) -> tuple[int, ...]:
        numbers = re.findall(r"\d+", version or "")
        return tuple(int(x) for x in numbers) if numbers else (0,)

    def _is_newer_version(self, current: str, remote: str) -> bool:
        cur = list(self._parse_version(current))
        rem = list(self._parse_version(remote))
        size = max(len(cur), len(rem))
        cur.extend([0] * (size - len(cur)))
        rem.extend([0] * (size - len(rem)))
        return tuple(rem) > tuple(cur)

    def _parse_patch_level(self, value: Any) -> int:
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            return 0

    def ensure_extensions(self) -> None:
        # Migrations legeres pour enrichir une base deja existante.
        with get_connection() as conn:
            with conn.cursor() as cursor:
                if is_sqlite():
                    cursor.execute(
                        """
                        CREATE TABLE IF NOT EXISTS stores (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            name TEXT NOT NULL UNIQUE,
                            address TEXT,
                            phone TEXT
                        )
                        """
                    )
                    cursor.execute(
                        """
                        CREATE TABLE IF NOT EXISTS cash_registers (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            store_id INTEGER NOT NULL,
                            name TEXT NOT NULL,
                            is_active INTEGER NOT NULL DEFAULT 1,
                            UNIQUE (store_id, name),
                            FOREIGN KEY (store_id) REFERENCES stores(id)
                        )
                        """
                    )
                    cursor.execute(
                        """
                        CREATE TABLE IF NOT EXISTS app_settings (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            setting_key TEXT NOT NULL UNIQUE,
                            setting_value TEXT
                        )
                        """
                    )
                else:
                    cursor.execute(
                        """
                        CREATE TABLE IF NOT EXISTS stores (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            name VARCHAR(120) NOT NULL UNIQUE,
                            address VARCHAR(255),
                            phone VARCHAR(40)
                        )
                        """
                    )
                    cursor.execute(
                        """
                        CREATE TABLE IF NOT EXISTS cash_registers (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            store_id INT NOT NULL,
                            name VARCHAR(80) NOT NULL,
                            is_active TINYINT(1) NOT NULL DEFAULT 1,
                            UNIQUE KEY uk_store_register (store_id, name),
                            FOREIGN KEY (store_id) REFERENCES stores(id)
                        )
                        """
                    )
                    cursor.execute(
                        """
                        CREATE TABLE IF NOT EXISTS app_settings (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            setting_key VARCHAR(120) NOT NULL UNIQUE,
                            setting_value TEXT
                        )
                        """
                    )
                cursor.execute("INSERT IGNORE INTO stores (id, name, address, phone) VALUES (1, 'Magasin Principal', '', '')")
                cursor.execute("INSERT IGNORE INTO cash_registers (id, store_id, name, is_active) VALUES (1, 1, 'Caisse 1', 1)")

                if not column_exists(conn, "users", "failed_attempts"):
                    cursor.execute("ALTER TABLE users ADD COLUMN failed_attempts INT NOT NULL DEFAULT 0")

                if not column_exists(conn, "users", "locked_until"):
                    cursor.execute("ALTER TABLE users ADD COLUMN locked_until DATETIME NULL")

                if not column_exists(conn, "users", "must_change_password"):
                    cursor.execute("ALTER TABLE users ADD COLUMN must_change_password TINYINT(1) NOT NULL DEFAULT 0")

                if not column_exists(conn, "sales", "store_id"):
                    cursor.execute("ALTER TABLE sales ADD COLUMN store_id INT NULL")

                if not column_exists(conn, "sales", "register_id"):
                    cursor.execute("ALTER TABLE sales ADD COLUMN register_id INT NULL")

                if not column_exists(conn, "purchase_orders", "store_id"):
                    cursor.execute("ALTER TABLE purchase_orders ADD COLUMN store_id INT NULL")

            conn.commit()

    def _password_policy_ok(self, password: str) -> bool:
        if len(password) < 8:
            return False
        has_upper = any(c.isupper() for c in password)
        has_lower = any(c.islower() for c in password)
        has_digit = any(c.isdigit() for c in password)
        return has_upper and has_lower and has_digit

    def startup_integrity_check(self) -> dict[str, Any]:
        issues: list[str] = []
        counts = {
            "products": int(fetch_one("SELECT COUNT(*) AS c FROM products")["c"]),
            "users": int(fetch_one("SELECT COUNT(*) AS c FROM users")["c"]),
            "sales": int(fetch_one("SELECT COUNT(*) AS c FROM sales")["c"]),
        }

        orphan_sales = int(
            fetch_one(
                """
                SELECT COUNT(*) AS c
                FROM sales s
                LEFT JOIN users u ON u.id = s.user_id
                WHERE u.id IS NULL
                """
            )["c"]
        )
        if orphan_sales:
            issues.append(f"{orphan_sales} vente(s) orpheline(s) sans utilisateur")

        orphan_sale_items = int(
            fetch_one(
                """
                SELECT COUNT(*) AS c
                FROM sale_items si
                LEFT JOIN products p ON p.id = si.product_id
                WHERE p.id IS NULL
                """
            )["c"]
        )
        if orphan_sale_items:
            issues.append(f"{orphan_sale_items} ligne(s) de vente orpheline(s) sans produit")

        negative_stock = int(fetch_one("SELECT COUNT(*) AS c FROM products WHERE stock_qty < 0")["c"])
        if negative_stock:
            issues.append(f"{negative_stock} produit(s) avec stock negatif")

        return {"ok": len(issues) == 0, "issues": issues, "counts": counts}

    def check_remote_update(self) -> dict[str, Any]:
        if not APP_UPDATE_URL:
            return {"enabled": False, "available": False}
        try:
            parsed = urlsplit(APP_UPDATE_URL)
            query = dict(parse_qsl(parsed.query, keep_blank_values=True))
            query["t"] = str(int(time.time()))
            bust_url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))

            with urlopen(bust_url, timeout=8) as response:
                payload = json.loads(response.read().decode("utf-8"))
            latest = str(payload.get("version", "")).strip()
            if not latest:
                return {"enabled": True, "available": False}
            remote_patch = self._parse_patch_level(payload.get("patch", payload.get("build", 0)))
            current_patch = int(APP_PATCH)
            is_newer_version = self._is_newer_version(APP_VERSION, latest)
            is_patch_update = (not is_newer_version) and (self._parse_version(APP_VERSION) == self._parse_version(latest)) and (remote_patch > current_patch)
            return {
                "enabled": True,
                "available": is_newer_version or is_patch_update,
                "current": APP_VERSION,
                "latest": latest,
                "current_patch": current_patch,
                "latest_patch": remote_patch,
                "url": str(payload.get("download_url", "")),
                "notes": str(payload.get("notes", "")),
            }
        except (URLError, TimeoutError, ValueError, json.JSONDecodeError):
            return {"enabled": True, "available": False}

    def create_auto_backup_if_needed(self) -> str | None:
        out_dir = BACKUPS_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        today_key = datetime.now().strftime("%Y%m%d")
        existing = list(out_dir.glob(f"backup_{today_key}_*.json"))
        if existing:
            return None

        tables = [
            "roles",
            "users",
            "categories",
            "suppliers",
            "clients",
            "products",
            "sales",
            "sale_items",
            "purchase_orders",
            "purchase_items",
            "stock_movements",
            "returns",
            "audit_logs",
        ]
        payload = {table: fetch_all(f"SELECT * FROM {table}") for table in tables}
        file_path = out_dir / f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        file_path.write_text(json.dumps(payload, default=str, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(file_path)

    def get_permissions(self, role_name: str) -> set[str]:
        base = {
            "dashboard:view",
            "reports:view",
            "pos:sell",
            "invoice:export",
        }
        if role_name == "Caissier":
            return base | {"clients:manage"}
        if role_name == "Gestionnaire":
            return base | {
                "products:manage",
                "categories:manage",
                "stock:manage",
                "suppliers:manage",
                "purchase:manage",
                "clients:manage",
            }
        return base | {
            "products:manage",
            "categories:manage",
            "stock:manage",
            "suppliers:manage",
            "purchase:manage",
            "clients:manage",
            "users:manage",
            "settings:manage",
        }

    def authenticate(self, username: str, password: str) -> dict[str, Any] | None:
        row = fetch_one(
            """
            SELECT u.id, u.full_name, u.username, u.password_hash, r.name AS role_name,
                   u.failed_attempts, u.locked_until, u.must_change_password
            FROM users u
            JOIN roles r ON r.id = u.role_id
            WHERE u.username = %s AND u.is_active = 1
            """,
            (username,),
        )
        if not row:
            return None
        if row.get("locked_until") and row["locked_until"] > datetime.now():
            return None
        if not verify_password(password, row["password_hash"]):
            attempts = int(row.get("failed_attempts") or 0) + 1
            lock_until = datetime.now().replace(microsecond=0)
            if attempts >= 5:
                execute(
                    "UPDATE users SET failed_attempts=%s, locked_until=DATE_ADD(NOW(), INTERVAL 15 MINUTE) WHERE id=%s",
                    (attempts, row["id"]),
                )
            else:
                execute("UPDATE users SET failed_attempts=%s WHERE id=%s", (attempts, row["id"]))
            return None
        execute("UPDATE users SET failed_attempts=0, locked_until=NULL WHERE id=%s", (row["id"],))
        return row

    def ensure_default_admin(self) -> None:
        existing = fetch_one("SELECT id FROM users WHERE username = 'admin'")
        if existing:
            return
        execute(
            """
            INSERT INTO users (full_name, username, password_hash, role_id)
            VALUES (%s, %s, %s, %s)
            """,
            ("Administrateur", "admin", hash_password("admin123"), 1),
        )

    def audit(self, user_id: int | None, action: str, details: str = "") -> None:
        execute(
            "INSERT INTO audit_logs (user_id, action, details) VALUES (%s, %s, %s)",
            (user_id, action, details),
        )

    def dashboard_metrics(self) -> dict[str, Any]:
        sales = fetch_one(
            """
            SELECT IFNULL(SUM(total_amount), 0) AS total,
                   COUNT(*) AS count,
                   IFNULL(AVG(total_amount), 0) AS avg_basket
            FROM sales
            WHERE DATE(created_at) = CURDATE()
            """
        )
        low_stock = fetch_one("SELECT COUNT(*) AS c FROM products WHERE stock_qty <= min_stock")
        today_margin = fetch_one(
            """
            SELECT IFNULL(SUM(si.qty * (si.unit_price - p.purchase_price)), 0) AS margin
            FROM sale_items si
            JOIN sales s ON s.id = si.sale_id
            JOIN products p ON p.id = si.product_id
            WHERE DATE(s.created_at) = CURDATE()
            """
        )
        top_products = fetch_all(
            """
            SELECT p.name, IFNULL(SUM(si.qty), 0) AS sold
            FROM products p
            LEFT JOIN sale_items si ON si.product_id = p.id
            GROUP BY p.id, p.name
            ORDER BY sold DESC
            LIMIT 5
            """
        )
        return {
            "today_revenue": float(sales["total"]),
            "today_sales_count": int(sales["count"]),
            "avg_basket": float(sales["avg_basket"]),
            "today_margin": float(today_margin["margin"]),
            "low_stock_count": int(low_stock["c"]),
            "top_products": top_products,
        }

    def get_setting(self, key: str, default: str = "") -> str:
        row = fetch_one("SELECT setting_value FROM app_settings WHERE setting_key=%s", (key,))
        return str(row["setting_value"]) if row and row.get("setting_value") is not None else default

    def set_setting(self, key: str, value: str) -> None:
        execute(
            """
            INSERT INTO app_settings (setting_key, setting_value)
            VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE setting_value=VALUES(setting_value)
            """,
            (key, value),
        )

    def get_recent_alerts(self, limit: int = 20) -> list[dict[str, Any]]:
        alerts = []
        for row in self.stock_alerts()[:10]:
            alerts.append(
                {
                    "level": "warning",
                    "title": "Stock faible",
                    "message": f"{row['name']} ({row['stock_qty']}/{row['min_stock']})",
                }
            )

        update = self.check_remote_update()
        if update.get("enabled") and update.get("available"):
            alerts.insert(
                0,
                {
                    "level": "info",
                    "title": "Mise a jour",
                    "message": f"Version {update.get('latest')} disponible",
                },
            )

        for log in fetch_all(
            """
            SELECT action, details, created_at
            FROM audit_logs
            ORDER BY id DESC
            LIMIT %s
            """,
            (max(0, limit - len(alerts)),),
        ):
            alerts.append(
                {
                    "level": "info",
                    "title": str(log["action"]),
                    "message": f"{log['details']} ({log['created_at']})",
                }
            )
        return alerts[:limit]

    def list_categories(self) -> list[dict[str, Any]]:
        return fetch_all("SELECT id, name FROM categories ORDER BY name")

    def add_category(self, name: str) -> int:
        return execute("INSERT INTO categories (name) VALUES (%s)", (name,))

    def list_products(self, search: str = "") -> list[dict[str, Any]]:
        like = f"%{search.strip()}%"
        return fetch_all(
            """
            SELECT p.id, p.name, p.barcode, IFNULL(c.name, '') AS category,
                   p.purchase_price, p.sale_price, p.brand, p.stock_qty, p.min_stock
            FROM products p
            LEFT JOIN categories c ON c.id = p.category_id
            WHERE p.name LIKE %s OR p.barcode LIKE %s OR IFNULL(p.brand, '') LIKE %s
            ORDER BY p.name
            """,
            (like, like, like),
        )

    def add_product(
        self,
        name: str,
        barcode: str,
        category_id: int | None,
        purchase_price: float,
        sale_price: float,
        brand: str,
        stock_qty: int,
        min_stock: int,
    ) -> int:
        return execute(
            """
            INSERT INTO products (name, barcode, category_id, purchase_price, sale_price, brand, stock_qty, min_stock)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (name, barcode, category_id, purchase_price, sale_price, brand, stock_qty, min_stock),
        )

    def update_product(
        self,
        product_id: int,
        name: str,
        barcode: str,
        category_id: int | None,
        purchase_price: float,
        sale_price: float,
        brand: str,
        stock_qty: int,
        min_stock: int,
    ) -> None:
        execute(
            """
            UPDATE products
            SET name=%s, barcode=%s, category_id=%s, purchase_price=%s, sale_price=%s,
                brand=%s, stock_qty=%s, min_stock=%s
            WHERE id=%s
            """,
            (name, barcode, category_id, purchase_price, sale_price, brand, stock_qty, min_stock, product_id),
        )

    def delete_product(self, product_id: int) -> None:
        execute("DELETE FROM products WHERE id=%s", (product_id,))

    def find_product_by_barcode(self, barcode: str) -> dict[str, Any] | None:
        return fetch_one(
            "SELECT id, name, barcode, sale_price, purchase_price, stock_qty FROM products WHERE barcode=%s",
            (barcode,),
        )

    def list_clients(self) -> list[dict[str, Any]]:
        return fetch_all("SELECT id, full_name, phone, email, address FROM clients ORDER BY full_name")

    def add_client(self, full_name: str, phone: str, email: str, address: str) -> int:
        return execute(
            "INSERT INTO clients (full_name, phone, email, address) VALUES (%s, %s, %s, %s)",
            (full_name, phone, email, address),
        )

    def delete_client(self, client_id: int) -> None:
        execute("DELETE FROM clients WHERE id=%s", (client_id,))

    def list_suppliers(self) -> list[dict[str, Any]]:
        return fetch_all("SELECT id, name, phone, email, address, supplied_products FROM suppliers ORDER BY name")

    def add_supplier(self, name: str, phone: str, email: str, address: str, supplied_products: str) -> int:
        return execute(
            """
            INSERT INTO suppliers (name, phone, email, address, supplied_products)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (name, phone, email, address, supplied_products),
        )

    def delete_supplier(self, supplier_id: int) -> None:
        execute("DELETE FROM suppliers WHERE id=%s", (supplier_id,))

    def create_sale(
        self,
        user_id: int,
        client_id: int | None,
        payment_mode: str,
        discount_amount: float,
        vat_rate: float,
        items: list[dict[str, Any]],
    ) -> str:
        if not items:
            raise ValueError("Aucun article dans la facture.")

        subtotal = sum(i["qty"] * i["unit_price"] for i in items)
        vat_amount = (subtotal - discount_amount) * vat_rate
        total_amount = subtotal - discount_amount + vat_amount
        invoice_number = f"FAC-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        context = self.get_runtime_context()

        with get_connection() as conn:
            try:
                with conn.cursor(dictionary=True) as cursor:
                    cursor.execute(
                        """
                        INSERT INTO sales (invoice_number, client_id, user_id, payment_mode,
                                           discount_amount, vat_amount, subtotal, total_amount, store_id, register_id)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            invoice_number,
                            client_id,
                            user_id,
                            payment_mode,
                            discount_amount,
                            vat_amount,
                            subtotal,
                            total_amount,
                            context["store_id"],
                            context["register_id"],
                        ),
                    )
                    sale_id = cursor.lastrowid

                    for line in items:
                        qty = int(line["qty"])
                        product_id = int(line["product_id"])
                        unit_price = float(line["unit_price"])
                        line_total = qty * unit_price

                        cursor.execute(
                            """
                            INSERT INTO sale_items (sale_id, product_id, qty, unit_price, line_total)
                            VALUES (%s, %s, %s, %s, %s)
                            """,
                            (sale_id, product_id, qty, unit_price, line_total),
                        )

                        cursor.execute(
                            "UPDATE products SET stock_qty = stock_qty - %s WHERE id = %s AND stock_qty >= %s",
                            (qty, product_id, qty),
                        )
                        if cursor.rowcount == 0:
                            raise ValueError("Stock insuffisant pour un produit de la facture.")

                        cursor.execute(
                            """
                            INSERT INTO stock_movements
                            (product_id, movement_type, qty_change, reference_type, reference_id, note)
                            VALUES (%s, 'Vente', %s, 'sale', %s, %s)
                            """,
                            (product_id, -qty, sale_id, f"Facture {invoice_number}"),
                        )

                conn.commit()
            except Exception:
                conn.rollback()
                raise

        return invoice_number

    def create_purchase(
        self,
        user_id: int,
        supplier_id: int,
        delivery_date: date | None,
        items: list[dict[str, Any]],
    ) -> str:
        if not items:
            raise ValueError("Aucun article dans l'approvisionnement.")

        po_number = f"APP-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        total_amount = sum(float(i["qty"]) * float(i["unit_cost"]) for i in items)
        context = self.get_runtime_context()

        with get_connection() as conn:
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO purchase_orders (po_number, supplier_id, user_id, delivery_date, total_amount, status, store_id)
                        VALUES (%s, %s, %s, %s, %s, 'Recu', %s)
                        """,
                        (po_number, supplier_id, user_id, delivery_date, total_amount, context["store_id"]),
                    )
                    purchase_id = cursor.lastrowid

                    for line in items:
                        qty = int(line["qty"])
                        product_id = int(line["product_id"])
                        unit_cost = float(line["unit_cost"])
                        line_total = qty * unit_cost

                        cursor.execute(
                            """
                            INSERT INTO purchase_items (purchase_id, product_id, qty, unit_cost, line_total)
                            VALUES (%s, %s, %s, %s, %s)
                            """,
                            (purchase_id, product_id, qty, unit_cost, line_total),
                        )
                        cursor.execute(
                            "UPDATE products SET stock_qty = stock_qty + %s, purchase_price = %s WHERE id = %s",
                            (qty, unit_cost, product_id),
                        )
                        cursor.execute(
                            """
                            INSERT INTO stock_movements
                            (product_id, movement_type, qty_change, reference_type, reference_id, note)
                            VALUES (%s, 'Approvisionnement', %s, 'purchase', %s, %s)
                            """,
                            (product_id, qty, purchase_id, f"Appro {po_number}"),
                        )

                conn.commit()
            except Exception:
                conn.rollback()
                raise

        return po_number

    def stock_alerts(self) -> list[dict[str, Any]]:
        return fetch_all(
            """
            SELECT id, name, barcode, stock_qty, min_stock
            FROM products
            WHERE stock_qty <= min_stock
            ORDER BY stock_qty ASC
            """
        )

    def stock_movements(self, limit: int = 100) -> list[dict[str, Any]]:
        return fetch_all(
            """
            SELECT sm.created_at, p.name AS product_name, sm.movement_type, sm.qty_change, sm.note
            FROM stock_movements sm
            JOIN products p ON p.id = sm.product_id
            ORDER BY sm.id DESC
            LIMIT %s
            """,
            (limit,),
        )

    def register_return(self, sale_invoice: str, product_id: int, qty: int, reason: str) -> int:
        with get_connection() as conn:
            try:
                with conn.cursor(dictionary=True) as cursor:
                    cursor.execute("SELECT id FROM sales WHERE invoice_number=%s", (sale_invoice,))
                    sale = cursor.fetchone()
                    if not sale:
                        raise ValueError("Facture introuvable.")
                    sale_id = sale["id"]

                    cursor.execute(
                        """
                        SELECT unit_price
                        FROM sale_items
                        WHERE sale_id=%s AND product_id=%s
                        ORDER BY id DESC
                        LIMIT 1
                        """,
                        (sale_id, product_id),
                    )
                    line = cursor.fetchone()
                    if not line:
                        raise ValueError("Produit non trouve dans cette facture.")
                    refund_amount = float(line["unit_price"]) * qty

                    cursor.execute(
                        """
                        INSERT INTO returns (sale_id, product_id, qty, refund_amount, reason)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (sale_id, product_id, qty, refund_amount, reason),
                    )
                    return_id = cursor.lastrowid
                    cursor.execute("UPDATE products SET stock_qty = stock_qty + %s WHERE id=%s", (qty, product_id))
                    cursor.execute(
                        """
                        INSERT INTO stock_movements
                        (product_id, movement_type, qty_change, reference_type, reference_id, note)
                        VALUES (%s, 'Retour produit', %s, 'return', %s, %s)
                        """,
                        (product_id, qty, return_id, reason[:200]),
                    )
                conn.commit()
                return return_id
            except Exception:
                conn.rollback()
                raise

    def sales_report(self, from_date: str, to_date: str) -> list[dict[str, Any]]:
        return fetch_all(
            """
            SELECT invoice_number, total_amount, payment_mode, created_at
            FROM sales
            WHERE DATE(created_at) BETWEEN %s AND %s
            ORDER BY created_at DESC
            """,
            (from_date, to_date),
        )

    def finance_summary(self, from_date: str, to_date: str) -> dict[str, Any]:
        row = fetch_one(
            """
            SELECT IFNULL(SUM(si.qty * (si.unit_price - p.purchase_price)), 0) AS gross_profit,
                   IFNULL(SUM(s.total_amount), 0) AS revenue
            FROM sales s
            LEFT JOIN sale_items si ON si.sale_id = s.id
            LEFT JOIN products p ON p.id = si.product_id
            WHERE DATE(s.created_at) BETWEEN %s AND %s
            """,
            (from_date, to_date),
        )
        expense_row = fetch_one(
            """
            SELECT IFNULL(SUM(total_amount), 0) AS expenses
            FROM purchase_orders
            WHERE DATE(created_at) BETWEEN %s AND %s
            """,
            (from_date, to_date),
        )
        base = row or {"gross_profit": 0, "revenue": 0}
        base["expenses"] = float(expense_row["expenses"]) if expense_row else 0.0
        return base

    def list_users(self) -> list[dict[str, Any]]:
        return fetch_all(
            """
            SELECT u.id, u.full_name, u.username, r.name AS role_name, u.is_active
            FROM users u
            JOIN roles r ON r.id = u.role_id
            ORDER BY u.full_name
            """
        )

    def list_roles(self) -> list[dict[str, Any]]:
        return fetch_all("SELECT id, name FROM roles ORDER BY id")

    def add_user(self, full_name: str, username: str, password: str, role_id: int) -> int:
        if not self._password_policy_ok(password):
            raise ValueError("Mot de passe faible: min 8 caracteres, majuscule, minuscule et chiffre.")
        return execute(
            "INSERT INTO users (full_name, username, password_hash, role_id) VALUES (%s, %s, %s, %s)",
            (full_name, username, hash_password(password), role_id),
        )

    def change_password(self, user_id: int, old_password: str, new_password: str) -> None:
        row = fetch_one("SELECT password_hash FROM users WHERE id=%s", (user_id,))
        if not row:
            raise ValueError("Utilisateur introuvable.")
        if not verify_password(old_password, row["password_hash"]):
            raise ValueError("Ancien mot de passe invalide.")
        if not self._password_policy_ok(new_password):
            raise ValueError("Mot de passe faible: min 8 caracteres, majuscule, minuscule et chiffre.")
        execute(
            "UPDATE users SET password_hash=%s, must_change_password=0 WHERE id=%s",
            (hash_password(new_password), user_id),
        )

    def toggle_user(self, user_id: int, is_active: bool) -> None:
        execute("UPDATE users SET is_active=%s WHERE id=%s", (1 if is_active else 0, user_id))

    def delete_user(self, user_id: int) -> None:
        user = fetch_one("SELECT id, username FROM users WHERE id=%s", (user_id,))
        if not user:
            raise ValueError("Utilisateur introuvable.")
        if user["username"] == "admin":
            raise ValueError("Le compte admin principal ne peut pas etre supprime.")

        sales_count = fetch_one("SELECT COUNT(*) AS c FROM sales WHERE user_id=%s", (user_id,))
        purchase_count = fetch_one("SELECT COUNT(*) AS c FROM purchase_orders WHERE user_id=%s", (user_id,))
        if int(sales_count["c"]) > 0 or int(purchase_count["c"]) > 0:
            raise ValueError("Utilisateur lie a un historique. Utilisez Activer/Desactiver.")

        execute("DELETE FROM users WHERE id=%s", (user_id,))

    def recent_sales(self, limit: int = 20) -> list[dict[str, Any]]:
        return fetch_all(
            """
            SELECT invoice_number, total_amount, payment_mode, created_at
            FROM sales
            ORDER BY id DESC
            LIMIT %s
            """,
            (limit,),
        )

    def recent_purchases(self, limit: int = 20) -> list[dict[str, Any]]:
        return fetch_all(
            """
            SELECT po_number, total_amount, status, created_at
            FROM purchase_orders
            ORDER BY id DESC
            LIMIT %s
            """,
            (limit,),
        )

    def list_stores(self) -> list[dict[str, Any]]:
        return fetch_all("SELECT id, name, address, phone FROM stores ORDER BY name")

    def list_registers(self, store_id: int) -> list[dict[str, Any]]:
        return fetch_all("SELECT id, name FROM cash_registers WHERE store_id=%s AND is_active=1 ORDER BY name", (store_id,))

    def get_runtime_context(self) -> dict[str, int]:
        store = fetch_one("SELECT setting_value FROM app_settings WHERE setting_key='active_store_id'")
        register = fetch_one("SELECT setting_value FROM app_settings WHERE setting_key='active_register_id'")
        return {
            "store_id": int(store["setting_value"]) if store and store["setting_value"] else 1,
            "register_id": int(register["setting_value"]) if register and register["setting_value"] else 1,
        }

    def set_runtime_context(self, store_id: int, register_id: int) -> None:
        execute(
            """
            INSERT INTO app_settings (setting_key, setting_value)
            VALUES ('active_store_id', %s)
            ON DUPLICATE KEY UPDATE setting_value=VALUES(setting_value)
            """,
            (str(store_id),),
        )
        execute(
            """
            INSERT INTO app_settings (setting_key, setting_value)
            VALUES ('active_register_id', %s)
            ON DUPLICATE KEY UPDATE setting_value=VALUES(setting_value)
            """,
            (str(register_id),),
        )

    def restore_backup_json(self, file_path: str) -> None:
        path = Path(file_path)
        if not path.exists():
            raise ValueError("Fichier introuvable.")
        payload = json.loads(path.read_text(encoding="utf-8"))

        truncate_order = [
            "sale_items",
            "purchase_items",
            "returns",
            "stock_movements",
            "sales",
            "purchase_orders",
            "products",
            "clients",
            "suppliers",
            "categories",
            "audit_logs",
            "users",
            "roles",
        ]
        insert_order = [
            "roles",
            "users",
            "categories",
            "suppliers",
            "clients",
            "products",
            "sales",
            "sale_items",
            "purchase_orders",
            "purchase_items",
            "stock_movements",
            "returns",
            "audit_logs",
        ]

        with get_connection() as conn:
            try:
                with conn.cursor() as cursor:
                    if is_sqlite():
                        cursor.execute("PRAGMA foreign_keys = OFF")
                    else:
                        cursor.execute("SET FOREIGN_KEY_CHECKS=0")
                    for table in truncate_order:
                        if is_sqlite():
                            cursor.execute(f"DELETE FROM {table}")
                        else:
                            cursor.execute(f"TRUNCATE TABLE {table}")

                    for table in insert_order:
                        rows = payload.get(table, [])
                        if not rows:
                            continue
                        cols = list(rows[0].keys())
                        placeholders = ",".join(["%s"] * len(cols))
                        col_sql = ",".join(cols)
                        sql = f"INSERT INTO {table} ({col_sql}) VALUES ({placeholders})"
                        data_rows = [tuple(row.get(col) for col in cols) for row in rows]
                        cursor.executemany(sql, data_rows)

                    if is_sqlite():
                        cursor.execute("PRAGMA foreign_keys = ON")
                    else:
                        cursor.execute("SET FOREIGN_KEY_CHECKS=1")
                conn.commit()
            except Exception:
                conn.rollback()
                raise
