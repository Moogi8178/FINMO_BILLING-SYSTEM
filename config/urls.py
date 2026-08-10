from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from billing import views as billing_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('billing.urls')),
    path('pay/<slug:slug>/', billing_views.purchase_page, name='purchase-page'),

    path('login/', auth_views.LoginView.as_view(template_name='billing/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('dashboard/', billing_views.dashboard_page, name='dashboard-page'),
    path('dashboard/subscribers/', billing_views.subscribers_page, name='subscribers-page'),
    path('dashboard/plans/', billing_views.plans_page, name='plans-page'),
    path('dashboard/billing/', billing_views.invoices_page, name='invoices-page'),
]
