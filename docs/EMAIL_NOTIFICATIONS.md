# Email notifications

ConstructSaaS uses the existing in-app notification stream as the source of truth and a database outbox for email delivery. Email is selective by default: only approvals, exceptions, returns, rejections, overdue records, and critical stock or budget warnings are queued. Routine completion updates stay in the app unless a user disables **Required action only** in Settings.

## Amazon SES setup

1. Verify the sending domain or address in Amazon SES.
2. If the SES account is still in sandbox mode, verify recipient addresses or request production access.
3. Create SES SMTP credentials for the selected AWS region.
4. Set the following variables on both `constructsaas-web` and `constructsaas-email-outbox` in Render:

   - `DJANGO_EMAIL_HOST`: the SES SMTP endpoint for the selected region
   - `DJANGO_EMAIL_HOST_USER`: SES SMTP username
   - `DJANGO_EMAIL_HOST_PASSWORD`: SES SMTP password
   - `DJANGO_DEFAULT_FROM_EMAIL`: a verified sender, such as `ConstructSaaS <alerts@example.com>`

The Blueprint supplies the SMTP backend, port 587, and TLS settings. Its cron job processes the outbox every two minutes. Render charges a minimum monthly amount for each cron service; the command can instead be run by another scheduler if desired.

## Operational checks

- Open **Settings → Email notifications** and confirm the status is **Ready**.
- Use **Send test email** to verify the signed-in user's saved email address.
- Review failed records in the `notifications_emaildelivery` table or run `python manage.py process_email_outbox` manually.
- Failed sends retry with backoff and never roll back the approval, receipt, invoice, or payment that produced the alert.
