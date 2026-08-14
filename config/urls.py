from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from billing import views as billing_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('billing.urls')),
    path('pay/<slug:slug>/', billing_views.purchase_page, name='purchase-page'),

    # Provider (WiFi business owner) dashboard
    path('login/', auth_views.LoginView.as_view(template_name='billing/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('dashboard/', billing_views.dashboard_page, name='dashboard-page'),
    path('dashboard/subscribers/', billing_views.subscribers_page, name='subscribers-page'),
    path('dashboard/plans/', billing_views.plans_page, name='plans-page'),
    path('dashboard/billing/', billing_views.invoices_page, name='invoices-page'),

    # Customer (WiFi subscriber) self-service accounts
    path('customer/register/<slug:slug>/', billing_views.customer_register_page, name='customer-register'),
    path('customer/login/<slug:slug>/', billing_views.customer_login_page, name='customer-login'),
    path('customer/dashboard/', billing_views.customer_dashboard_page, name='customer-dashboard'),
    path('customer/logout/', billing_views.customer_logout_page, name='customer-logout'),
    path('customer/buy/<int:package_id>/', billing_views.customer_buy_package, name='customer-buy-package'),

    # Password reset - shared flow for both provider and customer accounts,
    # since they're both plain Django Users under the hood
    path('password-reset/', auth_views.PasswordResetView.as_view(
        template_name='billing/password_reset.html',
        email_template_name='billing/password_reset_email.html',
        subject_template_name='billing/password_reset_subject.txt',
    ), name='password_reset'),
    path('password-reset/done/', auth_views.PasswordResetDoneView.as_view(
        template_name='billing/password_reset_done.html',
    ), name='password_reset_done'),
    path('password-reset-confirm/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='billing/password_reset_confirm.html',
    ), name='password_reset_confirm'),
    path('password-reset-complete/', auth_views.PasswordResetCompleteView.as_view(
        template_name='billing/password_reset_complete.html',
    ), name='password_reset_complete'),
]
