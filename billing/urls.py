from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register('providers', views.ProviderViewSet)
router.register('packages', views.PackageViewSet)
router.register('customers', views.CustomerViewSet)
router.register('invoices', views.InvoiceViewSet)
router.register('payments', views.PaymentViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('mpesa/stkpush/', views.initiate_payment, name='initiate-payment'),
    path('mpesa/callback/', views.mpesa_callback, name='mpesa-callback'),
    path('reports/dashboard/', views.dashboard_summary, name='dashboard-summary'),
    path('setup/create-admin/', views.create_superuser_once, name='create-superuser-once'),
    path('payments/<int:payment_id>/status/', views.payment_status, name='payment-status'),
]
