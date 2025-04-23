## ❓ Frequently Asked Questions (FAQ)

### 📚 API Documentation

**Q: Where can I find the API documentation?**  
**A:** The documentation is available at `/api/docs`.  
If you're running the project locally, visit [http://localhost:9060/api/docs](http://localhost:9060/api/docs).  
It provides an OpenAPI specification — everything should be clear from there.

---

### 🔐 Authentication

**Q: How does user authentication via API work?**  
**A:**  
The project is designed to be managed via SSO (e.g., [Fief](https://fief.dev)).  
Currently, authentication works via SSO or Django sessions for testing purposes.  
Token-based authentication is possible — PRs are welcome!  
You can integrate any OpenID-compliant SSO provider (like Keycloak).

---

### ⚙️ Admin Panel

**Q: How do I access the admin panel?**  
**A:** Like any Django project — go to `/admin/`.

**Q: Should I protect the admin panel in production?**  
**A:** Yes, it’s recommended. Use VPN solutions like OpenVPN, ZeroTier, etc.

---

### 🎨 Customization

**Q: Can I change the theme?**  
**A:** Yes! You can change colors, logo, and more directly from the admin panel.

---

### 📧 Notifications & Email Templates

**Q: Does the service support notifications and email templates?**  
**A:** Yes. The service triggers templates on certain events (e.g., `payment_success`, `subscription_canceled`).  
Templates can be customized in the admin panel to match your own structure.

---

### 🗄️ Database Support

**Q: Can I use a database other than PostgreSQL?**  
**A:** Technically yes — it’s Django. But currently, the DB settings are not extracted into environment variables.  
If needed, feel free to open an issue or submit a PR for this feature.
