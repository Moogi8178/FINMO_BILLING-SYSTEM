from django.contrib import admin
from django.urls import path, include
from billing import views as billing_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('billing.urls')),
    path('pay/<slug:slug>/', billing_views.purchase_page, name='purchase-page'),
]
