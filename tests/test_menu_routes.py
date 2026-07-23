import unittest
import uuid
import app as app_module


class MenuRoutesTestCase(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()
        with self.client.session_transaction() as session:
            session["username"] = "admin"
            session["role"] = "admin"

    def test_root_menu_page_renders(self):
        response = self.client.get("/settings/root_menu")
        self.assertEqual(response.status_code, 200)

    def test_sub_menu_page_renders(self):
        response = self.client.get("/settings/sub_menu")
        self.assertEqual(response.status_code, 200)

    def test_role_normalization_supports_admin_variants(self):
        self.assertEqual(app_module.normalize_role_name("Admin"), "admin")
        self.assertEqual(app_module.normalize_role_name("System Admin"), "system_admin")
        self.assertEqual(app_module.normalize_role_name("Lab Technician"), "lab_technician")

    def test_sidebar_menu_items_include_saved_submenu(self):
        root_items = [
            {
                "root_menu_id": 1,
                "name": "Reports",
                "icon_name": "fa-chart-line",
                "url": "/reports",
                "status": "Active",
                "display_order": 10,
            }
        ]
        sub_items = [
            {
                "sub_menu_id": 2,
                "root_menu_id": 1,
                "name": "Custom Reports",
                "icon_name": "fa-chart-line",
                "url": "/reports",
                "status": "Active",
                "display_order": 20,
            }
        ]

        items = app_module.build_sidebar_menu_items(root_items=root_items, sub_items=sub_items)

        self.assertEqual(items[0]["name"], "Reports")
        self.assertEqual(items[0]["children"][0]["name"], "Custom Reports")
        self.assertEqual(items[0]["children"][0]["url"], "/reports")

    def test_sidebar_menu_items_skip_reserved_settings_root(self):
        root_items = [
            {
                "root_menu_id": 1,
                "name": "Settings",
                "icon_name": "fa-gear",
                "url": "/settings",
                "status": "Active",
                "display_order": 10,
            },
            {
                "root_menu_id": 2,
                "name": "Reports",
                "icon_name": "fa-chart-line",
                "url": "/reports",
                "status": "Active",
                "display_order": 20,
            },
        ]

        items = app_module.build_sidebar_menu_items(root_items=root_items, sub_items=[])

        self.assertEqual([item["name"] for item in items], ["Reports"])

    def test_laboratory_dashboard_route_renders(self):
        response = self.client.get("/laboratory/dashboard")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/select_branch", response.headers["Location"])

    def test_edit_doctor_route_is_available(self):
        response = self.client.get("/edit_doctor/1")
        self.assertIn(response.status_code, {302, 200})

    def test_laboratory_menu_includes_lims_setting_sections(self):
        root_items = [
            {
                "root_menu_id": 1,
                "name": "Laboratory",
                "icon_name": "fa-flask",
                "url": "/laboratory/dashboard",
                "status": "Active",
                "display_order": 60,
            }
        ]
        sub_items = [
            {
                "sub_menu_id": 1,
                "root_menu_id": 1,
                "name": "LIMS Setting",
                "icon_name": "fa-vial",
                "url": "/lims_settings",
                "status": "Active",
                "display_order": 40,
            }
        ]

        items = app_module.build_sidebar_menu_items(root_items=root_items, sub_items=sub_items)
        laboratory_item = next(item for item in items if item["name"] == "Laboratory")
        child_urls = [child["url"] for child in laboratory_item["children"]]

        self.assertIn("/lims_settings/rate_category", child_urls)
        self.assertIn("/lims_settings/test", child_urls)

    def test_login_accepts_seeded_admin_without_database(self):
        response = self.client.post(
            "/login",
            data={"username": "admin", "password": "admin123"},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("/select_branch", response.headers["Location"])

    def test_branch_creation_is_visible_without_database(self):
        branch_name = f"North Branch {uuid.uuid4().hex[:6]}"

        login_response = self.client.post(
            "/login",
            data={"username": "admin", "password": "admin123"},
            follow_redirects=False,
        )
        self.assertEqual(login_response.status_code, 302)

        create_response = self.client.post(
            "/select_branch",
            data={
                "action": "create",
                "branch_name": branch_name,
                "branch_code": "NB-01",
                "branch_address": "Colombo",
                "contact_person": "Dr. Silva",
            },
            follow_redirects=False,
        )

        self.assertEqual(create_response.status_code, 302)
        self.assertEqual(create_response.headers.get("Location"), "/select_branch")

        view_response = self.client.get("/select_branch")
        html = view_response.get_data(as_text=True)

        self.assertEqual(view_response.status_code, 200)
        self.assertIn(branch_name, html)


if __name__ == "__main__":
    unittest.main()
