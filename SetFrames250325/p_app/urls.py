from django.urls import path
from . import views
from .views import *
from .views import forgot_password, reset_password, customer_list
from django.conf.urls.static import static

urlpatterns = [

    path('admin_view',views.admin_view,name='admin_view'),
    path('admin_add',views.admin_lense_add,name='admin_add'),
    path('admin_update/<int:pk>/',views.update_lens,name='admin_update'),
    path('admin_delete/<int:pk>/',views.admin_lense_delete,name='admin_delete'),
    path('register',user_register,name='register'),
    path('login',userLogin,name='login'),
    path('',home_page,name='homepage'),
    path('logout/', user_logout, name='logout'),
    path('allproducts',allProducts,name='allProducts'),
    path('view-product/<int:id>/',view_product),
    path('add-to-cart/<int:id>',views.addtocart),

    path('remove_from_wishlist/<int:product_id>/', views.remove_from_wishlist,name='remove_from_wishlist'),
    path('add_to_wishlist/<int:product_id>/', views.add_to_wishlist, name='add_to_wishlist'),
    path('wishlist/', views.wishlist, name='wishlist'),

    path('search/', views.searchresult, name='search'),

    path('my-cart',views.mycart, name='my-cart'),

    path('managecart/<int:id>/',views.managecart,name="managecart"),

    path("empty-cart/",views.emptycart),

    path("checkout",views.checkout,name='checkout'),
    path('my-orders',my_orders,name='my-orders'),
    path('display_orders', views.display_orders, name='display_orders'),
    path('update-order-status/<int:order_id>/', views.update_order_status, name='update_order_status'),
    path('download-invoice/<int:order_id>/', views.generate_pdf, name='download_invoice'),
    path('forgot_password/', forgot_password, name='forgot_password'),
    path('reset_password/<str:uidb64>/<str:token>/', reset_password, name='reset_password'),
    path('low_quantity/', views.low_quantity_products, name='low_quantity_products'),
    path('seller_register/', views.seller_register, name='seller_register'),
    path('seller/<int:seller_id>/products/', views.seller_products, name='seller_products'),
    path('add_category/', views.add_category, name='add_category'),
    path('seller/', views.seller_view, name='seller_view'),
    path('order-more/<int:lens_id>/', views.order_more, name='order_more'),
    path('purchase-orders/', views.purchase_order_list, name='purchase-orders'),
    path('accept_order/<int:order_id>/', views.accept_order, name='accept_order'),
    path('reject_order/<int:order_id>/', views.reject_order, name='reject_order'),
    path('products-by-category/', views.products_by_category, name='products_by_category'),
    path('cancel-order/<int:order_id>/', cancel_order, name='cancel_order'),
    path('suggest-eyewear/', views.suggest_eyewear, name='suggest_eyewear'),

    # Admin Dashboard URLs
    # path('admin/', views.admin_view, name='admin_view'),
    path('admin/dashboard/stats/', views.admin_dashboard_stats, name='admin_dashboard_stats'),
    path('admin/orders/', views.admin_order_management, name='admin_order_management'),
    path('admin/inventory/', views.admin_inventory_management, name='admin_inventory_management'),
    path('admin/customers/', views.admin_customer_management, name='admin_customer_management'),
    path('customer_list/', customer_list, name='customer_list'),
    path('get_user_orders/', views.get_user_orders, name='get_user_orders'),

    # Specialist URLs
    path('register-specialist/', views.register_specialist, name='register_specialist'),
    path('book-appointment/', views.book_appointment, name='book_appointment'),
    path('specialist-dashboard/', views.specialist_dashboard, name='specialist_dashboard'),
    path('my-appointments/', views.my_appointments, name='my_appointments'),
    path('generate_appointment_report/<str:report_type>/', views.generate_appointment_report, name='generate_appointment_report'),
    path('edit-appointment/<int:appointment_id>/', views.edit_appointment, name='edit_appointment'),
    path('cancel_appointment/', views.cancel_appointment, name='cancel_appointment'),
    path('appointments/', views.specialist_appointments, name='specialist_appointments'),
    path('patient/<int:appointment_id>/', views.patient_details, name='patient_details'),

    #access restricted page
    path('not_allowed/', views.not_allowed, name='not_allowed'),

    #review urls
    path('add_review/<int:order_id>/<int:product_id>/', views.add_review, name='add_review'),
    path('product-reviews/', views.admin_product_reviews, name='admin_product_reviews'),
    path('product-reviews/<int:id>/', product_reviews, name='product_reviews'),

    #sales report
    path('analysis/', SalesAnalysisView.as_view(), name='sales_analysis'),
    path('chart-data/', sales_chart_data, name='sales_chart_data'),

    #query tool
    path('query-tool/', views.query_tool, name='query_tool'),

    #profile urls
    path('profile/<int:user_id>/', views.user_profile, name='user_profile'),
    path('orders/', views.orders_list, name='orders_list'),
     path('get_order_details/', views.get_order_details, name='get_order_details'),

    # Add these to your urlpatterns list
    path('send-delete-account-otp/', views.send_delete_account_otp, name='send_delete_account_otp'),
    path('verify-delete-account-otp/', views.verify_delete_account_otp, name='verify_delete_account_otp'),    

    #chat bot
    path('chatbot/', views.chatbot, name='chatbot'),

    #product list
    path('product-list/', views.admin_product_list, name='product_list'),
    
]+ static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
