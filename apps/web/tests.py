from django.test import TestCase
from apps.accounts.models import Company, User


class WebAppRouteTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Route Test Construction')
        self.user = User.objects.create_user(
            username='route_admin',
            password='StrongPass123!',
            company=self.company,
            role=User.ROLE_ADMIN,
        )

    def test_root_serves_react_app(self):
        response = self.client.get('/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<div id="root"></div>', html=True)
        self.assertContains(response, '/static/web/assets/')

    def test_react_shell_does_not_embed_user_data(self):
        response = self.client.get('/')

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.user.username)

    def test_login_page_renders(self):
        response = self.client.get('/login/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<div id="root"></div>', html=True)

    def test_client_side_route_serves_same_react_shell(self):
        response = self.client.get('/projects/123/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<div id="root"></div>', html=True)
