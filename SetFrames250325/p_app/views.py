from django.shortcuts import render,redirect
from django.db import transaction
from .models import *
from django.db.models import Q, Sum, Count, F, Avg
from django.contrib import messages
from . forms import  checkoutform, ImageUploadForm
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import  Lense, Review
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.template.loader import get_template, render_to_string
from xhtml2pdf import pisa
from django.utils import timezone
from datetime import timedelta
import json
from django.utils.datastructures import MultiValueDictKeyError
from django.views.decorators.csrf import csrf_protect, csrf_exempt

def generate_pdf(request, order_id):
    # Retrieve order details based on order_id
    order = Orders.objects.get(pk=order_id)
    
    # Render HTML template for invoice
    template_path = 'invoice_template.html'
    context = {'order': order}
    template = get_template(template_path)
    html = template.render(context)
    
    # Create a PDF
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="invoice_{order_id}.pdf"'
    pisa_status = pisa.CreatePDF(html, dest=response)
    
    # Return PDF as response
    if pisa_status.err:
        return HttpResponse('We had some errors <pre>' + html + '</pre>')
    return response


def admin_view(request):
    # Get all products
    products = Lense.objects.all()
    
    # Calculate total products and low stock count
    total_products = products.count()
    low_stock_count = products.filter(p_quantity__lt=10).count()
    
    # Get orders data
    orders = Orders.objects.all()
    recent_orders = orders.order_by('-created_at')[:5]
    total_orders = orders.count()
    
    # Calculate total revenue from completed orders
    total_revenue = orders.filter(
        order_status="order completed"
    ).aggregate(Sum('total'))['total__sum'] or 0
    
    # Get total customers
    total_customers = UserDetails.objects.count()
    
    # Generate sales data for the chart (last 7 days)
    sales_dates = []
    sales_data = []
    
    for i in range(6, -1, -1):
        date = timezone.now().date() - timedelta(days=i)
        sales_dates.append(date.strftime('%Y-%m-%d'))
        daily_sales = Orders.objects.filter(
            created_at__date=date,
            order_status="order completed"
        ).aggregate(Sum('total'))['total__sum'] or 0
        sales_data.append(float(daily_sales))
    
    # Get top selling categories based on sales from completed orders
    top_categories = CartProduct.objects.filter(
        cart__orders__order_status="order completed"
    ).values(
        'product__cat__name'
    ).annotate(
        total_quantity=Sum('quantity')
    ).order_by('-total_quantity')[:5]
    
    category_labels = []
    category_data = []
    
    for cat in top_categories:
        if cat['product__cat__name']:  # Check if category exists
            category_labels.append(cat['product__cat__name'])
            category_data.append(cat['total_quantity'])
    
    # Format recent orders for display
    formatted_orders = []
    for order in recent_orders:
        formatted_orders.append({
            'order_id': order.id,
            'customer_name': f"{order.customer.first_name} {order.customer.last_name}" if order.customer else 'Anonymous',
            'total_amount': order.total,
            'status': order.order_status,
            'date': order.created_at.strftime('%Y-%m-%d %H:%M')
        })
    
    context = {
        'P': products,
        'total_products': total_products,
        'total_orders': total_orders,
        'total_revenue': total_revenue,
        'total_customers': total_customers,
        'recent_orders': formatted_orders,
        'low_stock_count': low_stock_count,
        'sales_dates': json.dumps(sales_dates),
        'sales_data': json.dumps(sales_data),
        'category_labels': json.dumps(category_labels),
        'category_data': json.dumps(category_data)
    }
    
    return render(request, 'admin_view.html', context)

def admin_dashboard_stats(request):
    """API endpoint for dashboard statistics"""
    try:
        # Daily sales for the last 30 days
        daily_sales = []
        for i in range(29, -1, -1):
            date = timezone.now().date() - timedelta(days=i)
            sales = Orders.objects.filter(
                created_at__date=date,
                order_status="order completed"
            ).aggregate(
                total_sales=Sum('total'),
                order_count=Count('id')
            )
            daily_sales.append({
                'date': date.strftime('%Y-%m-%d'),
                'sales': float(sales['total_sales'] or 0),
                'orders': sales['order_count']
            })
        
        # Top selling products
        top_products = CartProduct.objects.values(
            'product__p_name'
        ).annotate(
            total_quantity=Sum('quantity')
        ).order_by('-total_quantity')[:5]
        
        # Category-wise sales
        category_sales = CartProduct.objects.values(
            'product__cat__name'
        ).annotate(
            total_sales=Sum(F('quantity') * F('rate'))
        ).order_by('-total_sales')
        
        data = {
            'daily_sales': daily_sales,
            'top_products': list(top_products),
            'category_sales': list(category_sales)
        }
        return JsonResponse(data)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

def admin_order_management(request):
    """View for managing orders"""
    orders = Orders.objects.all().order_by('-created_at')
    
    # Filter orders based on status if provided
    status_filter = request.GET.get('status')
    if status_filter:
        orders = orders.filter(order_status=status_filter)
    
    # Search functionality
    search_query = request.GET.get('search')
    if search_query:
        orders = orders.filter(
            Q(customer__first_name__icontains=search_query) |
            Q(customer__last_name__icontains=search_query) |
            Q(id__icontains=search_query)
        )
    
    context = {
        'orders': orders,
        'order_statuses': ORDER_STATUS,
        'current_filter': status_filter,
        'search_query': search_query
    }
    return render(request, 'admin_orders.html', context)

def admin_inventory_management(request):
    """View for managing inventory"""
    products = Lense.objects.all().order_by('p_quantity')
    
    # Filter products
    category_filter = request.GET.get('category')
    if category_filter:
        products = products.filter(cat_id=category_filter)
    
    # Stock status filter
    stock_status = request.GET.get('stock_status')
    if stock_status == 'low':
        products = products.filter(p_quantity__lt=10)
    elif stock_status == 'out':
        products = products.filter(p_quantity=0)
    
    context = {
        'products': products,
        'categories': Category.objects.all(),
        'current_category': category_filter,
        'current_stock_status': stock_status
    }
    return render(request, 'admin_inventory.html', context)

def admin_customer_management(request):
    """View for managing customers"""
    customers = UserDetails.objects.all().order_by('-id')
    
    # Search functionality
    search_query = request.GET.get('search')
    if search_query:
        customers = customers.filter(
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(email__icontains=search_query)
        )
    
    # Order statistics for each customer
    for customer in customers:
        customer.total_orders = Orders.objects.filter(customer=customer).count()
        customer.total_spent = Orders.objects.filter(
            customer=customer,
            order_status="order completed"
        ).aggregate(Sum('total'))['total__sum'] or 0
    
    context = {
        'customers': customers,
        'search_query': search_query
    }
    return render(request, 'admin_customers.html', context)

def admin_lense_add(request):
    if request.method == "POST":
        try:
            name = request.POST['pname']
            desc = request.POST['pdesc']
            seller_id = request.POST.get('seller')
            seller = Seller.objects.get(id=seller_id)
            price = request.POST['pprice']
            quantity = request.POST['pquantity']
            image = request.FILES['pimage']
            category_id = request.POST['pcategory']
            shape = request.POST['shape']  # Get the shape from form
            cat = Category.objects.get(id=category_id)
        except MultiValueDictKeyError:
            messages.error(request, "Required field missing.")
            return redirect('admin_add')

        # Check if the price is valid
        if not price.isdigit() or int(price) <= 0:
            messages.error(request, "Please enter a valid price greater than 0.")
            return redirect('admin_add')

        if Lense.objects.filter(p_name=name).exists():
            messages.info(request, "Lens with this name already exists.")
            return redirect('admin_add')

        lense = Lense.objects.create(
            p_name=name, 
            p_desc=desc, 
            p_quantity=quantity, 
            p_price=price, 
            p_image=image, 
            shape=shape,  # Add shape to creation
            cat=cat, 
            seller=seller
        )
        lense.save()
        messages.success(request, "Product Added Successfully!")
        return redirect('admin_view')

    cat = Category.objects.all()
    seller = Seller.objects.all()
    shapes = Lense.SHAPE_CHOICES  # Get shape choices from model
    return render(request, 'admin_lenseadd.html', {
        "cat": cat, 
        "sell": seller,
        "shapes": shapes  # Pass shapes to template
    })

def update_lens(request, pk):
    lens = Lense.objects.get(pk=pk)
    if request.method == 'POST':
        lens.p_name = request.POST['pname']
        lens.p_desc = request.POST['pdesc']
        lens.category = Category.objects.get(id=request.POST['pcategory'])
        lens.p_quantity = request.POST['pquantity']
        lens.p_price = request.POST['pprice']
        if 'pimage' in request.FILES:
            lens.p_image = request.FILES['pimage']
        lens.save()
        return redirect('admin_view')
    categories = Category.objects.all()
    return render(request, 'admin_lenseupdate.html', {'lens': lens, 'cat': categories})


from decimal import Decimal
def admin_lense_update(request,pk):
    p = Lense.objects.get(pk=pk)
    
    if request.method == 'POST':
        if 'pname' in request.POST:
            p.p_name = request.POST['pname']
        if 'pdesc' in request.POST:
            p.p_desc = request.POST['pdesc']
        if 'pprice' in request.POST:
            price = request.POST['pprice']
            try:
                price = Decimal(price)
                if price <= 0:
                    messages.error(request, "Please enter a valid price greater than 0.")
                    return redirect('admin_update', pk=pk)
                p.p_price = price
            except ValueError:
                messages.error(request, "Please enter a valid numeric price.")
                return redirect('admin_update', pk=pk)
        if 'pquantity' in request.POST:
            p.p_quantity = request.POST['pquantity']
        if 'pimage' in request.FILES:
            p.p_image = request.FILES['pimage']
        
        p.save()

        messages.success(request, "Product Updated Successfully!")
        return redirect('admin_view')
    
    context = {'P': p}
    return render(request,'admin_lenseupdate.html',context)

def admin_lense_delete(request,pk):
    try:
        p = Lense.objects.filter(pk=pk)
        p.delete()
        messages.success(request,"Product Deleted Successfully!")
        return redirect('admin_view')
        # return HttpResponse("<h1 style='color:Black;text-align:center;margin-top:20%;'>Product Deleted Successfully</h1>")
    except Lense.DoesNotExist:
        messages.error(request,'Product Not Found')
        return redirect('admin_view')

from django.contrib import messages

from django.core.mail import send_mail
from django.shortcuts import render, redirect
from django.contrib import messages
from p_app.models import UserDetails, Seller  # Import your models

def user_register(request):
    if request.method == 'POST':
        first_name = request.POST.get('fname')
        last_name = request.POST.get('lname')
        username = request.POST.get('username')
        password = request.POST.get('password')
        email = request.POST.get('email')
        mobile_phone = request.POST.get('phone')

        # Check if username, email, or phone already exists
        if UserDetails.objects.filter(username=username).exists():
            messages.error(request, 'Username is already taken. Please choose a different one.')
            return render(request, 'register.html')

        if UserDetails.objects.filter(email=email).exists():
            messages.error(request, 'Email is already registered. Please use a different email.')
            return render(request, 'register.html')

        if UserDetails.objects.filter(mobile_phone=mobile_phone).exists():
            messages.error(request, 'Phone number is already registered. Please use a different number.')
            return render(request, 'register.html')

        # Proceed with registration if no duplicate found
        if first_name and last_name and username and password and email and mobile_phone:
            user = UserDetails.objects.create(
                first_name=first_name,
                last_name=last_name,
                username=username,
                password=password,
                email=email,
                mobile_phone=mobile_phone
            )
            user.save()
            return redirect('login')

    return render(request, 'register.html')


def seller_register(request):
    if request.method == 'POST':
        first_name = request.POST.get('fname')
        last_name = request.POST.get('lname')
        username = request.POST.get('username')
        password = request.POST.get('password')
        email = request.POST.get('email')
        mobile_phone = request.POST.get('phone')

        # Check if username, email, or phone already exists
        if Seller.objects.filter(username=username).exists():
            messages.error(request, 'Username is already taken. Please choose a different one.')
            return render(request, 'seller_register.html')

        if Seller.objects.filter(email=email).exists():
            messages.error(request, 'Email is already registered. Please use a different email.')
            return render(request, 'seller_register.html')

        if Seller.objects.filter(mobile_phone=mobile_phone).exists():
            messages.error(request, 'Phone number is already registered. Please use a different number.')
            return render(request, 'seller_register.html')

        # Proceed with registration if no duplicate found
        if first_name and last_name and username and password and email and mobile_phone:
            seller = Seller.objects.create(
                first_name=first_name,
                last_name=last_name,
                username=username,
                password=password,
                email=email,
                mobile_phone=mobile_phone
            )
            seller.save()

            # Send email to the seller
            subject = 'Your account has been created'
            message = f'Hi {username},\n\nYour seller account has been successfully created.\n\nUsername: {username}\nPassword: {password}\n\nThank you for registering!'
            from_email = 'bimalbabu720@gmail.com'  # Change this to your email
            to_email = email
            send_mail(subject, message, from_email, [to_email])

            return redirect('login')

    return render(request, 'seller_register.html')

    
def userLogin(request):
    if request.method == "POST":
        email=request.POST['email']
        password=request.POST['password']
        user=UserDetails.objects.filter(email=email,password=password)
        seller=Seller.objects.filter(username=email,password=password)
        admin=admin_login.objects.filter(username=email,password=password)
        specialist=EyeSpecialist.objects.filter(email=email,password=password)

        if len(user) >= 1:
            request.session['user_id']=user[0].id
            request.session['user_type']='user'
            return redirect('homepage')
        elif len(admin) >= 1:
            request.session['user_id']=admin[0].id
            request.session['user_type']='admin'
            return redirect('admin_view')
        elif len(seller) >= 1:
            request.session['user_id']=seller[0].id
            request.session['user_type']='seller'
            return redirect('seller_view')
        elif len(specialist) >= 1:
            request.session['user_id']=specialist[0].id
            request.session['user_type']='specialist'
            return redirect('specialist_dashboard')
        else:
            messages.info(request,'Invalid Username or Password')
            return redirect('login')
    else:
        return render(request,'login.html')
    
#custom restrictions
def restrict_to_customers(view_func):
    """Decorator to restrict access to UserDetails (customers) only."""
    def wrapper(request, *args, **kwargs):
        if request.session.get('user_type') != 'user':  # Only customers can access
            return redirect('not_allowed')  # Redirect to an access denied page
        return view_func(request, *args, **kwargs)
    return wrapper
def not_allowed(request):
    return render(request, 'not_allowed.html')

#404
def custom_404_view(request, exception):
    return render(request, '404.html', status=404)
    
def home_page(request):
    p = Lense.objects.all()[:3]
    context = {'P':p}
    return render(request,'home.html',context)

def user_logout(request):
    if 'user_id' in request.session:
        del request.session['user_id']
    return redirect('homepage')

from django.shortcuts import render
from .models import Lense, Category
from django.db.models import Q

def allProducts(request):
    # Get filters from GET parameters
    category_id = request.GET.get('category')  # Get the category ID from the query string
    shape = request.GET.get('shape')  # Get the shape filter
    query = request.GET.get('q', '')  # Search query
    min_price = request.GET.get('min_price')  # Min price filter
    max_price = request.GET.get('max_price')  # Max price filter
    min_rating = request.GET.get('min_rating')  # Min rating filter
    sort_option = request.GET.get('sort', 'price_asc')  # Sort option (default to 'price_asc')

    # Import Avg at the top of the function to use it throughout
    from django.db.models import Avg, Count

    # Start with all products and annotate with average rating immediately
    products = Lense.objects.all().annotate(
        avg_rating=Avg('reviews__rating'),
        review_count=Count('reviews')
    )

    # Filter by category if provided
    if category_id:
        products = products.filter(cat_id=category_id)

    # Filter by shape if provided
    if shape:
        products = products.filter(shape=shape)

    # Apply search query if provided
    if query:
        products = products.filter(Q(p_name__icontains=query) | Q(p_desc__icontains=query))

    # Apply price range filter if min_price and max_price are provided
    if min_price:
        products = products.filter(p_price__gte=min_price)  # Filter products with price >= min_price
    if max_price:
        products = products.filter(p_price__lte=max_price)  # Filter products with price <= max_price

    # Filter by minimum rating if provided
    if min_rating:
        products = products.filter(avg_rating__gte=min_rating)

    # Apply sorting based on user's selection
    if sort_option == 'price_asc':
        products = products.order_by('p_price')  # Sort by price ascending
    elif sort_option == 'price_desc':
        products = products.order_by('-p_price')  # Sort by price descending
    elif sort_option == 'rating_desc':
        # Sort by rating (highest first)
        products = products.order_by('-avg_rating', 'p_price')

    # Fetch all categories to display in the filter
    categories = Category.objects.all()
    
    # Get shape choices from model
    shapes = dict(Lense.SHAPE_CHOICES)
    
    # Get category names for display in active filters
    if category_id:
        try:
            selected_category_name = Category.objects.get(id=category_id).name
        except Category.DoesNotExist:
            selected_category_name = "Unknown Category"
    else:
        selected_category_name = None
        
    # Get shape name for display in active filters
    if shape:
        selected_shape_name = dict(Lense.SHAPE_CHOICES).get(shape, "Unknown Shape")
    else:
        selected_shape_name = None

    # Pass the filtered and sorted products, categories, shapes and rating options to the template
    context = {
        'P': products,
        'categories': categories,
        'shapes': shapes.items(),  # Pass shape choices to template
        'selected_category': category_id,  # To highlight the selected category in the dropdown
        'selected_category_name': selected_category_name,  # For display in active filters
        'selected_shape': shape,  # To highlight the selected shape in the dropdown
        'selected_shape_name': selected_shape_name,  # For display in active filters
        'selected_min_rating': min_rating,  # To show selected minimum rating
        'rating_options': range(1, 6),  # To display rating filter options (1-5)
    }

    return render(request, 'shop.html', context)

def view_product(request, id):
    # Retrieve the product by primary key (using your p_id field internally)
    perfume = get_object_or_404(Lense, pk=id)

    seller = perfume.seller
    # Fetch recommended products based on matching category or shape
    similar_products = Lense.objects.filter(
    Q(cat=perfume.cat) | Q(shape=perfume.shape)
    ).annotate(
        review_count=Count('reviews'),
        avg_rating=Avg('reviews__rating')
    ).exclude(pk=perfume.pk)[:4]   # Limit to 4 similar products

    # Fetch top-rated products with at least 2 reviews
    top_rated_products = Lense.objects.annotate(
        avg_rating=Avg('reviews__rating'),
        review_count=Count('reviews')
    ).filter(
        review_count__gte=2  # Only include products with at least 2 reviews
    ).order_by('-avg_rating')[:3]  # Get top 3 by average rating

    # Fetch most ordered products
    most_ordered_products = Lense.objects.annotate(
        order_count=Count('cartproduct')
    ).order_by('-order_count')[:3]  # Get top 3 most ordered products

    # Combine recommendations but ensure current product is excluded
    recommended_products = list(similar_products)
    
    # Add top rated if not already in list and not the current product
    for product in top_rated_products:
        if product.pk != perfume.pk and product not in recommended_products:
            recommended_products.append(product)
            
    # Add most ordered if not already in list and not the current product
    for product in most_ordered_products:
        if product.pk != perfume.pk and product not in recommended_products:
            recommended_products.append(product)
    
    # Limit to at most 6 recommendations total
    recommended_products = recommended_products[:6]

    # Retrieve reviews for this product ordered by most recent
    reviews = Review.objects.filter(product=perfume).order_by('-created_at')
    total_reviews = reviews.count()
    if total_reviews > 0:
        avg_rating = reviews.aggregate(Avg('rating'))['rating__avg']
        avg_rating = round(avg_rating, 1)
        recent_reviews = reviews[:5]  # Get the 5 most recent reviews
    else:
        avg_rating = 0
        recent_reviews = None

    context = {
        'perfume': perfume,
        'seller': seller,
        'recommended_products': recommended_products,
        'similar_products': similar_products[:3],  # Top 3 similar products
        'top_rated_products': top_rated_products,  # Top rated products
        'most_ordered_products': most_ordered_products,  # Most ordered products
        'messages': messages.get_messages(request),
        'recent_reviews': recent_reviews,
        'avg_rating': avg_rating,
        'total_reviews': total_reviews,
    }

    return render(request, 'product_detail.html', context)


@restrict_to_customers
def mycart(request):
    user_id = request.session['user_id']
    up = UserDetails.objects.get(id=int(user_id))
    cart_id = request.session.get('cart_id')
    if cart_id:
        cart1 = cart.objects.get(id=cart_id)
    else:
        cart1 = None
    context = {'cart': cart1,'u':up}


    return render(request, 'mycart.html', context)

@restrict_to_customers
def addtocart(request, id):
    try:
        product_obj = Lense.objects.get(p_id=id)
        cart_id = request.session.get('cart_id')

        if cart_id:
            cart_obj = cart.objects.get(id=cart_id)
            product_in_cart = cart_obj.cartproduct_set.filter(product=product_obj)

            # Item already exists in cart
            if product_in_cart.exists():
                messages.info(request, "This product is already in your cart.")
            else:
                cartproduct = CartProduct.objects.create(
                    cart=cart_obj,
                    product=product_obj,
                    rate=product_obj.p_price,
                    quantity=1,
                    subtotal=product_obj.p_price
                )
                cart_obj.total += product_obj.p_price
                cart_obj.save()
        else:
            user_id = request.session['user_id']
            up = UserDetails.objects.get(id=int(user_id))
            cart_obj = cart.objects.create(customer=up, total=0)
            request.session['cart_id'] = cart_obj.id
            print("new cart")
            cp = CartProduct.objects.create(
                cart=cart_obj,
                product=product_obj,
                rate=product_obj.p_price,
                quantity=1,
                subtotal=product_obj.p_price
            )
            cart_obj.total += product_obj.p_price
            cart_obj.save()
    except Exception as e:
        messages.error(request, f"Please log in to add to Cart!")
    return redirect("/")

def managecart(request, id):
    print("im in manage cart")
    action = request.GET.get("action")
    cp_obj = CartProduct.objects.get(id=id)
    cart_obj = cp_obj.cart

    if action == "inc":
        cp_obj.quantity += 1
        cp_obj.subtotal += cp_obj.rate
        cp_obj.save()
        cart_obj.total += cp_obj.rate
        cart_obj.save()
    elif action == "dcr":
        cp_obj.quantity -= 1
        cp_obj.subtotal -= cp_obj.rate
        cp_obj.save()
        cart_obj.total -= cp_obj.rate
        cart_obj.save()
        if cp_obj.quantity == 0:
            cp_obj.delete()
            del request.session['cart_id']
    elif action == 'rmv':
        cart_obj.total -= cp_obj.subtotal
        cart_obj.save()
        cp_obj.delete()
    else:
        pass
    return redirect('/my-cart')

def emptycart(request):
    cart_id=request.session.get("cart_id",None)
    cart1=cart.objects.get(id=cart_id)
    cart1.cartproduct_set.all().delete()
    cart1.total=0
    cart1.save()

    return redirect('/my-cart')

from django.db import transaction
from .models import Orders, CartProduct, Lense  # Import necessary models


def cancel_order(request, order_id):
    # Retrieve user_id from the session
    user_id = request.session.get('user_id')
    if not user_id:
        messages.error(request, "User ID not found in session.")
        return redirect('my-orders')  # Redirect if session user ID is missing
    
    # Get the UserDetails object for the current user
    up = get_object_or_404(UserDetails, id=int(user_id))
    
    # Retrieve the order for the logged-in user
    order = get_object_or_404(Orders, id=order_id, customer=up)

    if order.order_status not in ["order cancelled", "order completed"]:
        order.order_status = "order cancelled"
        order.save()

        # Restore product quantities
        for cart_product in order.cart.cartproduct_set.all():
            lens = cart_product.product
            lens.p_quantity += cart_product.quantity
            lens.save()

        messages.success(request, f"Order #{order.id} has been canceled.")
    else:
        messages.error(request, "This order cannot be canceled.")

    return redirect('my-orders')  # Redirect back to the user's order page

def checkout(request):
    user_id=request.session['user_id']
    user=UserDetails.objects.get(id=user_id)
    cart_id = request.session.get("cart_id")
    cart_obj = cart.objects.get(id=cart_id)
    form = checkoutform(request.POST)
    if request.method == "POST":
        order_status = "Order recived"
        address = request.POST["address"]
        mobile =request.POST["contact"]
        total = request.POST["total"]
        with transaction.atomic():
            cart_products = CartProduct.objects.filter(cart=cart_obj)
            for cart_product in cart_products:
                product = cart_product.product
                product.p_quantity -= cart_product.quantity
                product.save()
        new_order = Orders.objects.create(cart=cart_obj, customer=user, address=address, mobile=mobile,
                                              total=total, order_status=order_status)
        new_order.save()
        del request.session['cart_id']
        messages.info(request,"Order Placed")
        return redirect('/')
    else:
        context = {'cart': cart_obj, 'form': form,'user': user}
        return render(request, 'checkout.html', context)
    
@restrict_to_customers
def my_orders(request):
    user_id = request.session['user_id']
    up = UserDetails.objects.get(id=int(user_id))
    
    orders = Orders.objects.filter(customer=up).order_by('-created_at')
    
    # Get reviewed products for this user as (product_id, order_id) pairs
    reviewed_products = Review.objects.filter(user=up).values_list('product_id', 'order_id')
    reviewed_pairs = set((prod, ord_id) for prod, ord_id in reviewed_products)
    
    orders_data = []
    for order in orders:
        order_products_data = []
        for op in order.order_products:
            can_review = (
                order.order_status.lower() == "order completed" and 
                (op.product.p_id, order.id) not in reviewed_pairs
            )
            order_products_data.append({
                'order_product': op,
                'can_review': can_review,
            })
        orders_data.append({
            'order': order,
            'order_products': order_products_data,
        })
    
    return render(request, 'my_orders.html', {'orders_data': orders_data})



def searchresult(request):
    products = None
    query = None
    if 'q' in request.GET:
        query = request.GET.get('q')
        products = Lense.objects.all().filter(Q(p_name__contains=query) | Q(p_desc__contains=query) | Q(p_fragrance__contains=query) | Q(p_desc__contains=query))
        return render(request, 'search.html', {'query': query, 'products': products})
    
@restrict_to_customers
def wishlist(request):
    user_id = request.session['user_id']
    user_details = UserDetails.objects.get(id=int(user_id))
    
    # No need to get or create a Django User - use UserDetails directly
    wishlist = Wishlist.objects.filter(user=user_details)
    return render(request, 'wishlist.html', {'wishlist': wishlist})

def add_to_wishlist(request, product_id):
    if 'user_id' not in request.session:
        messages.error(request, "Please log in to add items to your wishlist")
        return redirect('login')
        
    user_id = request.session['user_id']
    user = UserDetails.objects.get(id=int(user_id))
    product = get_object_or_404(Lense, p_id=product_id)
    wishlist, created = Wishlist.objects.get_or_create(user=user)
    wishlist.products.add(product)
    messages.success(request, "Product added to your wishlist!")
    return redirect('wishlist')

def remove_from_wishlist(request, product_id):
    if 'user_id' not in request.session:
        messages.error(request, "Please log in to manage your wishlist")
        return redirect('login')
        
    user_id = request.session['user_id']
    user = UserDetails.objects.get(id=int(user_id))
    product = get_object_or_404(Lense, p_id=product_id)
    try:
        wishlist = Wishlist.objects.get(user=user)
        wishlist.products.remove(product)
        messages.success(request, "Product removed from your wishlist")
    except Wishlist.DoesNotExist:
        messages.error(request, "Wishlist not found")
    
    return redirect('wishlist')


def display_orders(request):
    """
    Enhanced order management view with sorting, filtering, searching and statistics
    """
    try:
        # Get base queryset with optimized prefetching
        orders = Orders.objects.all().select_related('customer').prefetch_related('cart__cartproduct_set__product')
        
        # Apply search filter if provided
        search_query = request.GET.get('search', '')
        if search_query:
            orders = orders.filter(
                Q(id__icontains=search_query) |
                Q(customer__username__icontains=search_query) |
                Q(customer__first_name__icontains=search_query) |
                Q(customer__last_name__icontains=search_query) |
                Q(customer__email__icontains=search_query) |
                Q(mobile__icontains=search_query) |
                Q(address__icontains=search_query)  # Add search by shipping address
            )
        
        # Apply status filter if provided
        status_filter = request.GET.get('status_filter', '')
        if status_filter:
            orders = orders.filter(order_status=status_filter)
        
        # Apply date range filter if provided
        date_from = request.GET.get('date_from', '')
        date_to = request.GET.get('date_to', '')
        if date_from:
            orders = orders.filter(created_at__date__gte=date_from)
        if date_to:
            orders = orders.filter(created_at__date__lte=date_to)
        
        # Get sort parameter from query string, default to '-created_at' (newest first)
        sort_by = request.GET.get('sort', '-created_at')
        
        # Apply sorting - negative sign means descending order
        valid_sort_fields = ['created_at', '-created_at', 'status', 'total', '-total', 'order_status', 'address']
        if sort_by in valid_sort_fields:
            orders = orders.order_by(sort_by)
        else:
            # Default to newest first
            orders = orders.order_by('-created_at')
            sort_by = '-created_at'  # Reset invalid sort parameter
        
        # Calculate order statistics
        total_orders = orders.count()
        pending_count = orders.filter(order_status='order recived').count() 
        processing_count = orders.filter(order_status='order processing').count()
        completed_count = orders.filter(order_status='order completed').count()
        cancelled_count = orders.filter(order_status='order cancelled').count()
        
        # Add pagination
        page = request.GET.get('page', 1)
        paginator = Paginator(orders, 10)  # Show 10 orders per page
        
        try:
            orders_page = paginator.page(page)
        except PageNotAnInteger:
            orders_page = paginator.page(1)
        except EmptyPage:
            orders_page = paginator.page(paginator.num_pages)
        
        # Create shipping address statistics (count orders by city or region)
        shipping_locations = {}
        for order in orders:
            # Extract city or region from address (simplified example)
            address = order.address if order.address else "Unknown"
            # Simple way to extract city - assumes format like "address, city, state"
            parts = address.split(',')
            location = parts[-2].strip() if len(parts) >= 2 else address
            
            if location in shipping_locations:
                shipping_locations[location] += 1
            else:
                shipping_locations[location] = 1
        
        # Get top shipping locations
        top_shipping_locations = dict(sorted(shipping_locations.items(), 
                                            key=lambda item: item[1], 
                                            reverse=True)[:5])
        
        context = {
            'orders': orders_page,
            'ORDER_STATUS': ORDER_STATUS,
            'current_sort': sort_by,
            'search_query': search_query,
            'status_filter': status_filter,
            'date_from': date_from,
            'date_to': date_to,
            'total_orders': total_orders,
            'pending_count': pending_count,
            'processing_count': processing_count,
            'completed_count': completed_count,
            'cancelled_count': cancelled_count,
            'shipping_locations': top_shipping_locations,  # Add shipping address statistics
        }
        return render(request, 'display_orders.html', context)
    
    except Exception as e:
        messages.error(request, f"An error occurred while loading orders: {str(e)}")
        return redirect('admin_view')  # Redirect to admin dashboard on error


def update_order_status(request, order_id):
    if request.method == 'POST':
        order = Orders.objects.get(id=order_id)
        new_status = request.POST.get('status')
        order.order_status = new_status
        order.save()
    return redirect('display_orders')


from django.conf import settings
from django.shortcuts import render, redirect
from django.contrib.auth.models import User
from django.contrib.auth import login, authenticate, logout
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.urls import reverse_lazy
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.decorators import login_required
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.contrib.auth import authenticate, login
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.contrib.auth.models import User
from django.http import HttpResponse, HttpResponseNotFound
from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.contrib import messages
from .models import *
from django.template.loader import get_template
from xhtml2pdf import pisa
from django.views import View


class CustomTokenGenerator(PasswordResetTokenGenerator):
    def _make_hash_value(self, user, timestamp):
        return (
            str(user.pk) + user.password + str(timestamp)
        )



def forgot_password(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        try:
            user = UserDetails.objects.get(email=email)
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = CustomTokenGenerator().make_token(user)
            reset_password_url = request.build_absolute_uri('/reset_password/{}/{}/'.format(uid, token))
            email_subject = 'Reset Your Password'

            # Render both HTML and plain text versions of the email
            email_body_html = render_to_string('reset_password_email.html', {
                'reset_password_url': reset_password_url,
                'user': user,
            })
            email_body_text = "Click the following link to reset your password: {}".format(reset_password_url)

            # Create an EmailMultiAlternatives object to send both HTML and plain text versions
            email = EmailMultiAlternatives(
                email_subject,
                email_body_text,
                settings.EMAIL_HOST_USER,
                [email],
            )
            email.attach_alternative(email_body_html, 'text/html')  # Attach HTML version
            email.send(fail_silently=False)

            messages.success(request, 'An email has been sent to your email address with instructions on how to reset your password.')
            return redirect('login')
        except UserDetails.DoesNotExist:
            messages.error(request, "User with this email does not exist.")
    return render(request, 'forgot_password.html')

def reset_password(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = UserDetails.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, UserDetails.DoesNotExist):
        user = None

    if user is not None and CustomTokenGenerator().check_token(user, token):
        if request.method == 'POST':
            new_password = request.POST.get('new_password')
            confirm_password = request.POST.get('confirm_password')

            if new_password == confirm_password:
                # Update the password hash manually
                user.password = new_password
                user.save()
                messages.success(request, "Password reset successfully. You can now login with your new password.")
                return redirect('login')
            else:
                messages.error(request, "Passwords do not match.")
        return render(request, 'reset_password.html')
    else:
        messages.error(request, "Invalid reset link. Please try again or request a new reset link.")
        return redirect('login')
    
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.mail import send_mail
from django.conf import settings

@receiver(post_save, sender=Lense)

def check_quantity_and_send_email(sender, instance, created, **kwargs):
    if int(instance.p_quantity) < 5:
        subject = 'Low Quantity Alert'
        message = f"The quantity of {instance.p_name} is now {instance.p_quantity}. Please restock."
        send_mail(subject, message, settings.EMAIL_HOST_USER, [settings.EMAIL_HOST_USER], fail_silently=False)

def low_quantity_products(request):
    # Get low quantity lenses
    low_quantity_lenses = Lense.objects.filter(p_quantity__lt=5)
    low_quantity_count = low_quantity_lenses.count()
    
    # Get top selling products based on completed orders and quantities
    from django.db.models import Count, Sum, F, Q
    
    # Method 1: Consider only completed orders
    top_selling_products = Lense.objects.annotate(
        total_ordered=Sum(
            'cartproduct__quantity',
            filter=Q(cartproduct__cart__orders__order_status='order completed')
        )
    ).exclude(
        total_ordered=None
    ).order_by('-total_ordered')[:5]
    
    # Method 2: Get revenue-generating products
    top_revenue_products = Lense.objects.annotate(
        total_revenue=Sum(
            F('cartproduct__quantity') * F('cartproduct__rate'),
            filter=Q(cartproduct__cart__orders__order_status='order completed')
        )
    ).exclude(
        total_revenue=None
    ).order_by('-total_revenue')[:5]
    
    # Method 3: Get recently ordered products
    from django.utils import timezone
    from datetime import timedelta
    thirty_days_ago = timezone.now() - timedelta(days=30)
    
    recent_popular_products = Lense.objects.filter(
        cartproduct__cart__orders__created_at__gte=thirty_days_ago,
        cartproduct__cart__orders__order_status='order completed'
    ).annotate(
        recent_orders=Count('cartproduct__cart__orders', distinct=True)
    ).order_by('-recent_orders')[:5]
    
    return render(request, 'low_quantity_products.html', {
        'low_quantity_count': low_quantity_count, 
        'low_quantity_lenses': low_quantity_lenses,
        'top_selling_products': top_selling_products,
        'top_revenue_products': top_revenue_products,
        'recent_popular_products': recent_popular_products
    })

from .forms import CategoryForm

def add_category(request):
    if request.method == 'POST':
        form = CategoryForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('admin_view')  # Redirect to the category list page
    else:
        form = CategoryForm()
    return render(request, 'add_category.html', {'form': form})

# def seller_view(request):
#     if 'user_id' in request.session:
#         user_id = request.session['user_id']
#         try:
#             seller = Seller.objects.get(id=user_id)
#             purchase_orders = PurchaseOrder.objects.filter(seller=seller)
#             return render(request, 'seller_view.html', {'seller': seller, 'purchase_orders': purchase_orders})
#         except Seller.DoesNotExist:
#             # Handle the case where the seller with the given ID does not exist
#             return redirect('login')
#     else:
#         return redirect('login') # Redirect to login page if user is not logged in
    
from .models import PurchaseOrder
from .forms import OrderForm 

import logging

logger = logging.getLogger(__name__)

def order_more(request, lens_id):
    lens = get_object_or_404(Lense, pk=lens_id)
    if request.method == 'POST':
        form = OrderForm(request.POST)
        if form.is_valid():
            try:
                quantity = form.cleaned_data['quantity']
                unit_price = lens.p_price
                total_cost = quantity * unit_price
                # Retrieve the seller associated with the lens
                seller = lens.seller
                # Create a PurchaseOrder object
                purchase_order = PurchaseOrder.objects.create(
                    lens=lens,
                    quantity=quantity,
                    seller=seller,
                    total_amount=total_cost,
                    status='PENDING'  # You can set the status as required
                )
                # Save the purchase order
                purchase_order.save()
                return redirect('purchase-orders')  # Redirect to a success URL after order placement
            except Exception as e:
                # Log the error
                logger.error(f"Error creating PurchaseOrder: {e}")
                # Render the form with an error message
                form.add_error(None, "An error occurred while processing your order. Please try again later.")
        # If form is not valid, render the form with validation errors
        else:
            logger.warning(f"Form validation failed: {form.errors}")
    else:
        form = OrderForm()
    return render(request, 'order_more.html', {'form': form, 'lens': lens})

def purchase_order_list(request):
    """View for displaying purchase orders with seller analysis"""
    
    # Get base queryset
    orders = PurchaseOrder.objects.select_related('lens', 'seller')
    
    # Apply filters if provided
    seller_id = request.GET.get('seller', '')
    status = request.GET.get('status', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    product_id = request.GET.get('product', '')
    
    if seller_id:
        orders = orders.filter(seller_id=seller_id)
    if status:
        orders = orders.filter(status=status)
    if date_from:
        orders = orders.filter(purchase_date__gte=date_from)
    if date_to:
        orders = orders.filter(purchase_date__lte=date_to)
    if product_id:
        orders = orders.filter(lens_id=product_id)
    
    # Get all sellers for the filter dropdown
    sellers = Seller.objects.all()
    
    # Calculate overall statistics
    total_orders = orders.count()
    total_value = orders.aggregate(total=Sum('total_amount'))['total'] or 0
    pending_count = orders.filter(status='PENDING').count()
    delivered_count = orders.filter(status='DELIVERED').count()
    cancelled_count = orders.filter(status='CANCELLED').count()
    
    # Seller analysis
    seller_analysis = []
    
    # Group by seller using values() and annotate()
    seller_stats = orders.values('seller__id', 'seller__username').annotate(
        order_count=Count('id'),
        total_value=Sum('total_amount'),
        pending_count=Count('id', filter=Q(status='PENDING')),
        delivered_count=Count('id', filter=Q(status='DELIVERED')),
        cancelled_count=Count('id', filter=Q(status='CANCELLED')),
        avg_order_value=Avg('total_amount'),
        latest_order_date=Max('purchase_date')
    ).order_by('-order_count')
    
    # For each seller in the stats, get their top products
    for stat in seller_stats:
        seller_id = stat['seller__id']
        
        # Get top products for this seller
        top_products = orders.filter(
            seller_id=seller_id
        ).values(
            'lens__p_id', 
            'lens__p_name'
        ).annotate(
            order_count=Count('id'),
            total_quantity=Sum('quantity')
        ).order_by('-total_quantity')[:3]
        
        # Get recent orders for this seller
        recent_orders = orders.filter(
            seller_id=seller_id
        ).order_by('-purchase_date')[:3]
        
        # Add to seller analysis
        seller_analysis.append({
            'seller_id': seller_id,
            'seller_name': stat['seller__username'],
            'order_count': stat['order_count'],
            'total_value': stat['total_value'],
            'pending_count': stat['pending_count'],
            'delivered_count': stat['delivered_count'],
            'cancelled_count': stat['cancelled_count'],
            'avg_order_value': stat['avg_order_value'],
            'latest_order_date': stat['latest_order_date'],
            'top_products': list(top_products),
            'recent_orders': recent_orders
        })
    
    # Pagination for orders
    paginator = Paginator(orders, 15)  # Show 15 orders per page
    page_number = request.GET.get('page')
    orders_page = paginator.get_page(page_number)
    
    context = {
        'orders': orders_page,
        'sellers': sellers,
        'seller_analysis': seller_analysis,
        'selected_seller': seller_id,
        'selected_status': status,
        'date_from': date_from,
        'date_to': date_to,
        'selected_product': product_id,
        'total_orders': total_orders,
        'total_value': total_value,
        'pending_count': pending_count,
        'delivered_count': delivered_count,
        'cancelled_count': cancelled_count,
    }
    
    return render(request, 'purchase_order_list.html', context)

from django.db.models import Sum, Count, Avg, F, Q, Case, When, Value, IntegerField, DecimalField, FloatField
from django.db.models.functions import TruncMonth, TruncWeek, TruncDay, Coalesce
from datetime import datetime, timedelta
import json

def seller_view(request):
    if 'user_id' in request.session:
        user_id = request.session['user_id']
        try:
            seller = Seller.objects.get(id=user_id)
            
            # Get time period for filtering (default to last 30 days)
            period = request.GET.get('period', '30days')
            if period == '7days':
                start_date = datetime.now() - timedelta(days=7)
                date_format = '%d %b'
            elif period == '90days':
                start_date = datetime.now() - timedelta(days=90)
                date_format = '%b %Y'
            elif period == 'year':
                start_date = datetime.now() - timedelta(days=365)
                date_format = '%b %Y'
            else:  # Default 30 days
                start_date = datetime.now() - timedelta(days=30)
                date_format = '%d %b'
                
            # Get all purchase orders for this seller
            all_purchase_orders = PurchaseOrder.objects.filter(seller=seller)
            
            # Dashboard metrics - use explicit output_field for aggregations
            metrics = {
                'total_orders': all_purchase_orders.count(),
                'pending_orders': all_purchase_orders.filter(status='PENDING').count(),
                'delivered_orders': all_purchase_orders.filter(status='DELIVERED').count(),
                'cancelled_orders': all_purchase_orders.filter(status='CANCELLED').count(),
                'total_revenue': float(all_purchase_orders.filter(status='DELIVERED').aggregate(
                    total=Sum('total_amount')
                )['total'] or 0),
                'avg_order_value': float(all_purchase_orders.filter(status='DELIVERED').aggregate(
                    avg=Avg('total_amount')
                )['avg'] or 0),
            }
            
            # Get recent orders for display in the dashboard
            recent_orders = all_purchase_orders.order_by('-purchase_date')[:10]
            
            # Choose time truncation based on period
            if period == '7days':
                trunc_func = TruncDay
            elif period == '90days' or period == 'year':
                trunc_func = TruncMonth
            else:  # Default 30 days
                trunc_func = TruncDay

            # Get the data separately to avoid mixed type issues
            time_series = all_purchase_orders.filter(
                purchase_date__gte=start_date
            ).annotate(
                date=trunc_func('purchase_date')
            ).values('date', 'status', 'total_amount')

            # Process data manually
            chart_data_dict = {}
            
            for entry in time_series:
                if entry['date']:
                    date_str = entry['date'].strftime(date_format)
                    if date_str not in chart_data_dict:
                        chart_data_dict[date_str] = {'revenue': 0, 'orders': 0}
                    
                    chart_data_dict[date_str]['orders'] += 1
                    
                    if entry['status'] == 'DELIVERED':
                        chart_data_dict[date_str]['revenue'] += float(entry['total_amount'])
            
            # Sort by date and convert to format needed for chart
            dates = sorted(chart_data_dict.keys())
            
            chart_data = {
                'labels': dates,
                'revenue': [chart_data_dict[date]['revenue'] for date in dates],
                'orders': [chart_data_dict[date]['orders'] for date in dates]
            }
            
            # If no data, provide fallback
            if not dates:
                chart_data = {
                    'labels': ["Jan", "Feb", "Mar", "Apr", "May"],
                    'revenue': [500.0, 600.0, 400.0, 700.0, 800.0],
                    'orders': [5, 8, 4, 7, 9]
                }
            
            # Top selling products
            top_products = Lense.objects.filter(
                seller=seller
            ).annotate(
                ordered_quantity=Sum(
                    Case(
                        When(purchaseorder__status='DELIVERED', then='purchaseorder__quantity'),
                        default=Value(0),
                        output_field=IntegerField()
                    )
                ),
                revenue=Sum(
                    Case(
                        When(purchaseorder__status='DELIVERED', then='purchaseorder__total_amount'),
                        default=Value(0),
                        output_field=DecimalField()
                    )
                )
            ).exclude(
                ordered_quantity=0
            ).order_by('-ordered_quantity')[:5]
            
            # Low stock products
            low_stock_products = Lense.objects.filter(
                seller=seller,
                p_quantity__lt=10
            ).order_by('p_quantity')
            
            # Status trends - simplified calculation
            status_trends = []
            for i in range(4, -1, -1):
                month_start = datetime.now().replace(day=1) - timedelta(days=30*i)
                month_end = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
                
                month_orders = all_purchase_orders.filter(purchase_date__range=[month_start, month_end])
                total = month_orders.count()
                pending = month_orders.filter(status='PENDING').count()
                delivered = month_orders.filter(status='DELIVERED').count()
                cancelled = month_orders.filter(status='CANCELLED').count()
                
                month_data = {
                    'month': month_start.strftime('%b %Y'),
                    'pending': pending,
                    'delivered': delivered,
                    'cancelled': cancelled,
                    'pending_percent': round(pending / total * 100, 1) if total > 0 else 0,
                    'delivered_percent': round(delivered / total * 100, 1) if total > 0 else 0,
                    'cancelled_percent': round(cancelled / total * 100, 1) if total > 0 else 0,
                }
                status_trends.append(month_data)
            
            context = {
                'seller': seller,
                'purchase_orders': recent_orders,
                'metrics': metrics,
                'chart_data': json.dumps(chart_data),
                'top_products': top_products,
                'low_stock_products': low_stock_products,
                'status_trends': status_trends,
                'selected_period': period,
            }
            
            return render(request, 'seller_view.html', context)
        except Seller.DoesNotExist:
            return redirect('login')
    else:
        return redirect('login')

def accept_order(request, order_id):
    if 'user_id' in request.session:
        try:
            order = PurchaseOrder.objects.get(id=order_id)
            order.status = 'DELIVERED'
            order.save()
            # Update quantity in Lense model
            order.lens.p_quantity += order.quantity
            order.lens.save()
            # Send email notification
            send_mail(
                'Purchase Order Accepted',
                f'Your purchase order for {order.quantity} {order.lens.p_name} from {order.lens.seller.username} has been accepted. Total amount: {order.total_amount}',
                'your_email@example.com',
                ['bimalbabu720@gmail.com'],
                fail_silently=False,
                html_message=f'''
                <!DOCTYPE html>
                <html>
                <head>
                    <style>
                        body {{
                            font-family: Arial, sans-serif;
                            line-height: 1.6;
                            color: #333;
                            max-width: 600px;
                            margin: 0 auto;
                        }}
                        .container {{
                            padding: 20px;
                            border: 1px solid #e0e0e0;
                            border-radius: 5px;
                            background-color: #f9f9f9;
                        }}
                        .header {{
                            background-color: #4CAF50;
                            color: white;
                            padding: 15px;
                            text-align: center;
                            border-radius: 5px 5px 0 0;
                            margin-bottom: 20px;
                        }}
                        .details {{
                            background-color: white;
                            padding: 15px;
                            border-radius: 5px;
                            margin-bottom: 20px;
                            border-left: 4px solid #4CAF50;
                        }}
                        .footer {{
                            text-align: center;
                            margin-top: 20px;
                            font-size: 0.8em;
                            color: #666;
                        }}
                        .button {{
                            display: inline-block;
                            background-color: #4CAF50;
                            color: white;
                            padding: 10px 20px;
                            text-decoration: none;
                            border-radius: 5px;
                            margin-top: 15px;
                        }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <div class="header">
                            <h2>Purchase Order Accepted</h2>
                        </div>
                        
                        <p>Good news! Your purchase order has been accepted.</p>
                        
                        <div class="details">
                            <p><strong>Product:</strong> {order.lens.p_name}</p>
                            <p><strong>Quantity:</strong> {order.quantity}</p>
                            <p><strong>Seller:</strong> {order.lens.seller.username}</p>
                            <p><strong>Total Amount:</strong> ₹{order.total_amount}</p>
                        </div>
                        
                        <p>Your order is now being processed and will be shipped soon.</p>
                        
                        <div style="text-align: center;">
                            <a href="#" class="button">Track Your Order</a>
                        </div>
                        
                        <div class="footer">
                            <p>Thank you for shopping with SetFrames!</p>
                            <p>If you have any questions, please contact our customer support.</p>
                        </div>
                    </div>
                </body>
                </html>
                '''
            )
        except PurchaseOrder.DoesNotExist:
            pass  # Handle case where order does not exist
    return redirect('seller_view')

def reject_order(request, order_id):
    if 'user_id' in request.session:
        try:
            order = PurchaseOrder.objects.get(id=order_id)
            order.status = 'CANCELLED'
            order.save()
            # Send email notification
            send_mail(
                'Purchase Order Rejected',
                f'Your purchase order for {order.quantity} {order.lens.p_name} has been rejected by {order.lens.seller.username}',
                'your_email@example.com',
                ['bimalbabu720@gmail.com'],
                fail_silently=False,
            )
        except PurchaseOrder.DoesNotExist:
            pass  # Handle case where order does not exist
    return redirect('seller_view')

def products_by_category(request):
    categories = Category.objects.all()  # Retrieve all categories

    # Check if category filter is applied
    category_id = request.GET.get('category')
    if category_id:
        category = Category.objects.get(pk=category_id)
        products = Lense.objects.filter(category=category)
    else:
        # If no category is selected, display all products
        products = Lense.objects.all()

    context = {
        'categories': categories,
        'products': products
    }
    return render(request, 'shop.html', context)

# myapp/views.py
from django.shortcuts import render
from django.http import JsonResponse
from .forms import ImageUploadForm
from .models import Lense
import os
import google.generativeai as genai
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponseBadRequest
import re

genai.configure(api_key=os.environ["GEMINI_API_KEY"])

def upload_to_gemini(path, mime_type=None):
    file = genai.upload_file(path, mime_type=mime_type)
    print(f"Uploaded file '{file.display_name}' as: {file.uri}")
    return file

generation_config = {
    "temperature": 1,
    "top_p": 0.95,
    "top_k": 40,
    "max_output_tokens": 8192,
    "response_mime_type": "text/plain",
}

model = genai.GenerativeModel(
    model_name="gemini-1.5-pro",
    generation_config=generation_config,
    system_instruction="Find a suitable eyewear frame based on the face image. If it is not a face, please provide a valid human face image.",
)

SHAPE_RECOMMENDATIONS = {
    'oval': ['square', 'rectangle', 'aviator', 'geometric'],
    'round': ['rectangular', 'square', 'geometric', 'aviator'],
    'square': ['round', 'oval', 'aviator'],
    'rectangle': ['round', 'oval', 'geometric'],
    'heart': ['oval', 'round', 'square'],
    'diamond': ['oval', 'round', 'geometric']
}

def extract_face_shape(response_text):
    """Extract face shape from Gemini's response more accurately"""
    face_shapes = ['oval', 'round', 'square', 'rectangle', 'heart', 'diamond']
    
    # Convert response to lowercase for better matching
    text_lower = response_text.lower()
    
    # Look for explicit face shape mentions
    for shape in face_shapes:
        if f"{shape} face" in text_lower or f"{shape}-shaped face" in text_lower:
            return shape
            
    return None

@csrf_exempt
def suggest_eyewear(request):
    suggestions = []
    error = None
    filtered_lenses = []
    detected_shape = None
    
    if request.method == 'POST':
        form = ImageUploadForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                image = form.cleaned_data['image']
                path = default_storage.save('tmp/' + image.name, ContentFile(image.read()))
                tmp_file = os.path.join(default_storage.location, path)

                file = upload_to_gemini(tmp_file, mime_type="image/jpeg")
                
                # Modify the system instruction to be more specific
                model.system_instruction = """
                Analyze the face image and determine the face shape. 
                Explicitly state the face shape (oval, round, square, rectangle, heart, or diamond) 
                and then recommend suitable eyewear frames. 
                Format the response as:
                Face Shape: [SHAPE]
                Recommended Frames:
                - [Frame type 1]
                - [Frame type 2]
                """

                chat_session = model.start_chat()
                response = chat_session.send_message([
                    "Please analyze this face image and recommend suitable eyewear frames",
                    file
                ])

                # Extract face shape
                detected_shape = extract_face_shape(response.text)
                
                if detected_shape:
                    # Get recommended frame shapes
                    recommended_shapes = SHAPE_RECOMMENDATIONS.get(detected_shape, [])
                    
                    # Filter lenses based on recommended shapes
                    filtered_lenses = Lense.objects.filter(shape__in=recommended_shapes)
                    
                    suggestions = [
                        f"Based on your {detected_shape} face shape, we recommend:",
                        *[f"{shape.title()} frames" for shape in recommended_shapes]
                    ]
                else:
                    error = "Could not determine face shape. Please try another image."
                
            except Exception as e:
                error = f"Error processing image: {str(e)}"
            finally:
                # Clean up temporary file
                if 'tmp_file' in locals():
                    default_storage.delete(path)
    else:
        form = ImageUploadForm()

    return render(request, 'upload.html', {
        'form': form,
        'suggestions': suggestions,
        'filtered_lenses': filtered_lenses,
        'error': error,
        'detected_shape': detected_shape
    })

from django.db import connection
from django.db.models import Count, Sum, Avg, F, Q, Case, When, Value, Max, DecimalField
from django.db.models.functions import Coalesce
from django.shortcuts import render
from django.core.paginator import Paginator

def customer_list(request):
    """
    View for displaying customer list with analytics and insights
    """
    # Get sort parameter from request (default to total_spent)
    sort_by = request.GET.get('sort', 'total_spent')
    order = request.GET.get('order', 'desc')
    search_query = request.GET.get('q', '')
    
    # Base query with annotations for metrics - FIXED to only include completed orders
    users = UserDetails.objects.annotate(
        total_orders=Count('orders', distinct=True),
        completed_orders=Count('orders', 
            filter=Q(orders__order_status="order completed"),
            distinct=True),
        total_spent=Coalesce(Sum(
            'orders__total',
            filter=Q(orders__order_status="order completed")
        ), 0),
        last_order_date=Max('orders__created_at'),
        avg_order_value=Case(
            When(completed_orders__gt=0, then=F('total_spent') / F('completed_orders')),
            default=Value(0),
            output_field=DecimalField()
        ),
        product_count=Count('orders__cart__cartproduct__product', 
            filter=Q(orders__order_status="order completed"),
            distinct=True)
    )
    
    # Apply search filter if provided
    if search_query:
        users = users.filter(
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(mobile_phone__icontains=search_query)
        )
    
    # Apply ordering
    order_prefix = '-' if order == 'desc' else ''
    valid_sort_fields = ['total_spent', 'total_orders', 'last_order_date', 
                         'avg_order_value', 'first_name', 'product_count']
    
    if sort_by in valid_sort_fields:
        users = users.order_by(f'{order_prefix}{sort_by}')
    else:
        users = users.order_by('-total_spent')  # Default sort
    
    # Get products for users
    for user in users:
        # Get top 3 products for this user
        top_products = []
        try:
            # Get cart IDs for this user's COMPLETED orders only
            cart_ids = Orders.objects.filter(
                customer_id=user.id,
                order_status="order completed"  # Exact match for completed orders
            ).values_list('cart_id', flat=True)
            
            # Get top products from these carts
            if cart_ids:
                # First try with direct relationship
                products_data = CartProduct.objects.filter(
                    cart_id__in=cart_ids
                ).values(
                    'product_id',
                    'product__p_name'  # Try to get name directly
                ).annotate(
                    quantity=Sum('quantity')
                ).order_by('-quantity')[:3]
                
                # Process the products
                for product in products_data:
                    product_name = product.get('product__p_name')
                    
                    # If name is not available through direct relation, try to look it up
                    if not product_name:
                        try:
                            from p_app.models import Lense
                            product_obj = Lense.objects.get(p_id=product['product_id'])
                            product_name = product_obj.p_name
                        except:
                            product_name = f"Product {product['product_id']}"
                    
                    top_products.append({
                        'name': product_name,
                        'quantity': product['quantity']
                    })
        except Exception as e:
            print(f"Error getting products for user {user.id}: {e}")
        
        # Always set the top_products attribute
        user.top_products = top_products
    
    # Calculate overall metrics for dashboard - FIXED to match admin calculation
    # Only count COMPLETED orders for revenue
    total_customers = users.count()
    active_customers = users.filter(completed_orders__gt=0).count()
    
    # Use a separate query to get exact total revenue to match admin
    total_revenue = Orders.objects.filter(
        order_status="order completed"
    ).aggregate(
        total=Sum('total')
    )['total'] or 0
    
    avg_customer_value = total_revenue / active_customers if active_customers > 0 else 0
    
    context = {
        'users': users,
        'sort_by': sort_by,
        'order': order,
        'search_query': search_query,
        'metrics': {
            'total_customers': total_customers,
            'active_customers': active_customers,
            'total_revenue': total_revenue,
            'avg_customer_value': avg_customer_value,
        }
    }
    
    return render(request, 'customer_list.html', context)

from django.http import JsonResponse

def get_user_orders(request):
    """API endpoint to get orders for a specific user"""
    user_id = request.GET.get('user_id')
    if not user_id:
        return JsonResponse({'error': 'User ID is required'}, status=400)
    
    try:
        # Get the user's recent orders (limit to 5)
        orders = Orders.objects.filter(
            customer_id=user_id
        ).order_by('-created_at')[:5]
        
        # Format the orders for the response
        orders_data = []
        for order in orders:
            orders_data.append({
                'id': order.id,
                'total': float(order.total),
                'order_status': order.order_status,
                'created_at': order.created_at.isoformat(),
                'products_count': order.cart.cartproduct_set.count() if order.cart else 0
            })
        
        return JsonResponse({'orders': orders_data})
    
    except Exception as e:
        print(f"Error in get_user_orders: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)
    
from django.shortcuts import render
from django.db.models import Count, Sum, Q, F
from django.core.paginator import Paginator
from .models import Orders, CartProduct
import traceback  # Add this import at the top of your file

def get_order_details(request):
    """API endpoint to get detailed information about a specific order"""
    order_id = request.GET.get('order_id')
    if not order_id:
        return JsonResponse({'error': 'Order ID is required'}, status=400)
    
    try:
        # Get the order with explicit error handling
        try:
            order = Orders.objects.get(id=order_id)
        except Orders.DoesNotExist:
            return JsonResponse({'error': 'Order not found'}, status=404)
        
        # Get products for this order
        products = []
        if order.cart:
            try:
                cart_products = CartProduct.objects.filter(cart_id=order.cart_id)
                
                for cp in cart_products:
                    # Get product name - try different approaches if needed
                    try:
                        if hasattr(cp, 'product') and hasattr(cp.product, 'p_name'):
                            product_name = cp.product.p_name
                        else:
                            # If product relation doesn't work, try getting it directly
                            from p_app.models import Lense
                            product = Lense.objects.get(p_id=cp.product_id)
                            product_name = product.p_name
                    except Exception:
                        product_name = f"Product {cp.product_id}"
                    
                    # Get price - use realistic fallbacks
                    try:
                        if hasattr(cp, 'rate') and cp.rate:
                            price = float(cp.rate)
                        elif hasattr(cp.product, 'p_price') and cp.product.p_price:
                            price = float(cp.product.p_price)
                        else:
                            # Set a default price
                            price = 0.0
                    except Exception:
                        price = 0.0
                    
                    products.append({
                        'name': product_name,
                        'quantity': cp.quantity,
                        'price': price
                    })
            except Exception as e:
                print(f"Error loading cart products: {e}")
                products = []
        
        # Format customer info if available
        customer_info = None
        if order.customer:
            customer_info = {
                'id': order.customer.id,
                'name': f"{order.customer.first_name} {order.customer.last_name}",
                'email': order.customer.email,
                'phone': order.customer.mobile_phone
            }
        
        # Format order data
        order_data = {
            'id': order.id,
            'created_at': order.created_at.isoformat(),
            'total': float(order.total),
            'order_status': order.order_status,
            'address': order.address or "No address provided",
            'mobile': order.mobile or "No contact provided",
            'customer': customer_info,
            'products': products
        }
        
        return JsonResponse({'order': order_data})
    
    except Exception as e:
        print(f"Error in get_order_details: {str(e)}")
        print(traceback.format_exc())  # Print full traceback for debugging
        return JsonResponse({'error': str(e)}, status=500)
    

def orders_list(request):
    """
    View for displaying orders with filtering options
    """
    # Get filter parameters
    customer_id = request.GET.get('customer')
    status = request.GET.get('status')
    search_query = request.GET.get('q', '')
    sort_by = request.GET.get('sort', 'created_at')
    order = request.GET.get('order', 'desc')
    
    # Base query
    orders = Orders.objects.all()
    
    # Apply customer filter if provided
    if customer_id:
        orders = orders.filter(customer_id=customer_id)
        # Get customer details for the header
        try:
            from .models import UserDetails
            customer = UserDetails.objects.get(id=customer_id)
        except:
            customer = None
    else:
        customer = None
    
    # Apply status filter if provided
    if status:
        orders = orders.filter(order_status=status)
    
    # Apply search filter if provided
    if search_query:
        orders = orders.filter(
            Q(id__icontains=search_query) |
            Q(customer__first_name__icontains=search_query) |
            Q(customer__last_name__icontains=search_query) |
            Q(customer__email__icontains=search_query) |
            Q(address__icontains=search_query)
        )
    
    # Apply ordering
    order_prefix = '-' if order == 'desc' else ''
    valid_sort_fields = ['id', 'created_at', 'total', 'order_status']
    
    if sort_by in valid_sort_fields:
        orders = orders.order_by(f'{order_prefix}{sort_by}')
    else:
        orders = orders.order_by('-created_at')  # Default to most recent
    
    # Annotate with product count
    orders = orders.annotate(
        product_count=Count('cart__cartproduct', distinct=True)
    )
    
    # Enrich with product information for each order
    for order in orders:
        # Get products for this order
        try:
            cart_products = CartProduct.objects.filter(
                cart_id=order.cart_id
            ).select_related('product')
            
            # Get the products with quantities
            products = []
            for cp in cart_products:
                product_name = getattr(cp.product, 'p_name', f'Product {cp.product_id}')
                products.append({
                    'name': product_name,
                    'quantity': cp.quantity,
                    'price': cp.price if hasattr(cp, 'price') else 0
                })
            
            order.products = products
        except Exception as e:
            print(f"Error getting products for order {order.id}: {e}")
            order.products = []
    
    # Pagination
    items_per_page = request.GET.get('items', 10)
    try:
        items_per_page = int(items_per_page)
    except ValueError:
        items_per_page = 10
    
    paginator = Paginator(orders, items_per_page)
    page = request.GET.get('page', 1)
    try:
        orders_page = paginator.page(page)
    except:
        orders_page = paginator.page(1)
    
    # Get order status options for filter dropdown
    from .models import ORDER_STATUS
    status_options = [status[0] for status in ORDER_STATUS]
    
    # Calculate metrics
    total_orders = orders.count()
    completed_orders = orders.filter(order_status="order completed").count()
    total_revenue = orders.filter(order_status="order completed").aggregate(Sum('total'))['total__sum'] or 0
    
    # For customer-specific view
    if customer:
        customer_metrics = {
            'name': f"{customer.first_name} {customer.last_name}",
            'email': customer.email,
            'phone': customer.mobile_phone,
            'total_orders': total_orders,
            'completed_orders': completed_orders,
            'total_spent': total_revenue
        }
    else:
        customer_metrics = None
    
    context = {
        'orders': orders_page,
        'sort_by': sort_by,
        'order': order,
        'search_query': search_query,
        'status': status,
        'status_options': status_options,
        'customer_id': customer_id,
        'customer': customer_metrics,
        'metrics': {
            'total_orders': total_orders,
            'completed_orders': completed_orders,
            'total_revenue': total_revenue,
        },
        'items_per_page': items_per_page
    }
    
    return render(request, 'orders.html', context)


# Helper function to convert cursor results to dictionaries
def dictfetchall(cursor):
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]

from django.core.mail import send_mail
from django.conf import settings
from .models import EyeSpecialist, Appointment
from django.contrib import messages
from django.utils.crypto import get_random_string

def register_specialist(request):
    if request.method == 'POST':
        # Get form data
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip()
        clinic_name = request.POST.get('clinic_name', '').strip()
        address = request.POST.get('address', '').strip()
        city = request.POST.get('city', '').strip()
        state = request.POST.get('state', '').strip()
        phone = request.POST.get('phone', '').strip()

        # Validation checks
        errors = []

        # Required fields validation
        if not all([first_name, last_name, email, clinic_name, address, city, state, phone]):
            errors.append("All fields are required.")

        # Name validation
        if len(first_name) < 2 or len(last_name) < 2:
            errors.append("First name and last name must be at least 2 characters long.")
        if not all(c.isalpha() or c.isspace() for c in first_name + last_name):
            errors.append("Names should only contain letters and spaces.")

        # Email validation
        email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_regex, email):
            errors.append("Please enter a valid email address.")
        if EyeSpecialist.objects.filter(email=email).exists():
            errors.append("A specialist with this email already exists.")

        # Phone validation
        phone_regex = r'^\d{10}$'
        if not re.match(phone_regex, phone):
            errors.append("Phone number must be 10 digits.")
        if EyeSpecialist.objects.filter(phone=phone).exists():
            errors.append("A specialist with this phone number already exists.")

        # Clinic name validation
        if EyeSpecialist.objects.filter(clinic_name=clinic_name).exists():
            errors.append("A clinic with this name already exists.")
        if len(clinic_name) < 3:
            errors.append("Clinic name must be at least 3 characters long.")

        # Address validation
        if len(address) < 10:
            errors.append("Please enter a complete address (minimum 10 characters).")

        # City and State validation
        if len(city) < 2 or len(state) < 2:
            errors.append("City and state must be at least 2 characters long.")

        # If there are any errors, return them to the template
        if errors:
            for error in errors:
                messages.error(request, error)
            # Return the form with the previously entered data
            context = {
                'form_data': request.POST,
                'errors': errors
            }
            return render(request, 'register_specialist.html', context)

        try:
            # Generate random password
            password = get_random_string(10)

            # Create specialist with transaction
            with transaction.atomic():
                specialist = EyeSpecialist.objects.create(
                    first_name=first_name,
                    last_name=last_name,
                    email=email,
                    password=password,
                    clinic_name=clinic_name,
                    address=address,
                    city=city,
                    state=state,
                    phone=phone
                )

                subject = 'Welcome to SetFrames - Your Eye Specialist Account'
                message = f'''<!DOCTYPE html>
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
    <div style="background-color: #f8f9fa; padding: 20px; border-radius: 5px; margin-bottom: 20px;">
        <h2 style="color: #2c3e50; margin-bottom: 20px; text-align: center;">Welcome to SetFrames</h2>
        <p style="font-size: 16px; margin-bottom: 15px;">Dear Dr. {first_name} {last_name},</p>
        <p style="margin-bottom: 20px;">Your eye specialist account has been successfully created. Below are your login credentials:</p>
        
        <div style="background-color: #ffffff; padding: 15px; border-left: 4px solid #3498db; margin-bottom: 20px;">
            <p style="margin: 5px 0;"><strong>Email:</strong> {email}</p>
            <p style="margin: 5px 0;"><strong>Password:</strong> {password}</p>
        </div>
        
        <div style="background-color: #fff3cd; padding: 10px; border-radius: 4px; margin-bottom: 20px;">
            <p style="color: #856404; margin: 0;">⚠️ Please change your password after your first login for security.</p>
        </div>
        
        <div style="background-color: #ffffff; padding: 15px; border-radius: 4px; margin-bottom: 20px;">
            <h3 style="color: #2c3e50; margin-top: 0;">Clinic Details</h3>
            <p style="margin: 5px 0;"><strong>Name:</strong> {clinic_name}</p>
            <p style="margin: 5px 0;"><strong>Address:</strong> {address}</p>
            <p style="margin: 5px 0;"><strong>City:</strong> {city}</p>
            <p style="margin: 5px 0;"><strong>State:</strong> {state}</p>
        </div>
        
        <p style="color: #721c24; background-color: #f8d7da; padding: 10px; border-radius: 4px;">
            🔒 For security reasons, please delete this email after memorizing your credentials.
        </p>
        
        <div style="text-align: center; margin-top: 30px; padding-top: 20px; border-top: 1px solid #dee2e6;">
            <p style="color: #6c757d; font-size: 14px;">Thank you for joining SetFrames</p>
            <p style="color: #6c757d; font-size: 12px;">If you didn't create this account, please contact support immediately.</p>
        </div>
    </div>
</body>
</html>'''
                try:
                    send_mail(
                        subject,
                        message,  # Plain text fallback
                        settings.DEFAULT_FROM_EMAIL,
                        [email],
                        fail_silently=False,
                        html_message=message  # HTML version
                    )
                except Exception as e:
                    # Log the error but don't prevent account creation
                    print(f"Email sending failed: {str(e)}")
                    messages.warning(request, "Account created but email notification failed.")

            messages.success(request, 'Specialist registered successfully')
            return redirect('admin_view')

        except Exception as e:
            messages.error(request, f"Error creating specialist account: {str(e)}")
            return redirect('register_specialist')

    return render(request, 'register_specialist.html')


@restrict_to_customers
def book_appointment(request):
    if 'user_id' not in request.session:
        messages.error(request, 'Please login first')
        return redirect('login')
    
    # Check if we're editing an existing appointment
    edit_id = request.GET.get('edit')
    editing_appointment = None
    if edit_id:
        try:
            editing_appointment = Appointment.objects.get(
                id=edit_id,
                patient_id=request.session['user_id'],
                status='PENDING'
            )
        except Appointment.DoesNotExist:
            messages.error(request, 'Appointment not found or cannot be edited')
            return redirect('my_appointments')
    
    if request.method == 'POST':
        specialist_id = request.POST.get('specialist')
        appointment_date = request.POST.get('appointment_date')
        appointment_time = request.POST.get('appointment_time')
        reason = request.POST.get('reason')
        
        if not specialist_id:
            messages.error(request, 'Please select a specialist')
            return redirect('book_appointment')

        # Check if user has an active appointment with this specialist
        existing_user_appointment = Appointment.objects.filter(
            patient_id=request.session['user_id'],
            specialist_id=specialist_id
        ).exclude(status__in=['CANCELLED', 'COMPLETED'])
        
        # If editing, exclude the current appointment from the check
        if editing_appointment:
            existing_user_appointment = existing_user_appointment.exclude(id=editing_appointment.id)
        
        if existing_user_appointment.exists():
            messages.error(request, 'You already have an active appointment with this specialist. Please wait until it is completed or cancelled.')
            return redirect('book_appointment')

        # Convert appointment date and time to datetime object
        try:
            appointment_datetime = datetime.strptime(
                f"{appointment_date} {appointment_time}", 
                "%Y-%m-%d %H:%M"
            )
            current_datetime = datetime.now()

            # Check if appointment datetime is in the past
            if appointment_datetime < current_datetime:
                messages.error(request, 'Cannot book appointments in the past')
                return redirect('book_appointment')

        except ValueError:
            messages.error(request, 'Invalid date or time format')
            return redirect('book_appointment')
        
        # Rest of your existing validation code...
        existing_appointment = Appointment.objects.filter(
            specialist_id=specialist_id,
            appointment_date=appointment_date,
            appointment_time=appointment_time
        )
        
        if editing_appointment:
            existing_appointment = existing_appointment.exclude(id=editing_appointment.id)
        
        if existing_appointment.exists():
            messages.error(request, 'This time slot is already booked. Please choose another time.')
            return redirect('book_appointment')
        
        try:
            specialist = EyeSpecialist.objects.get(id=specialist_id)
            patient = UserDetails.objects.get(id=request.session['user_id'])
            
            if editing_appointment:
                # Update existing appointment
                editing_appointment.specialist = specialist
                editing_appointment.appointment_date = appointment_date
                editing_appointment.appointment_time = appointment_time
                editing_appointment.reason = reason
                editing_appointment.save()
                messages.success(request, 'Appointment updated successfully')
            else:
                # Create new appointment
                Appointment.objects.create(
                    patient=patient,
                    specialist=specialist,
                    appointment_date=appointment_date,
                    appointment_time=appointment_time,
                    reason=reason,
                    status='PENDING'
                )
                messages.success(request, 'Appointment booked successfully')
            
            return redirect('my_appointments')
            
        except Exception as e:
            messages.error(request, f'Error processing appointment: {str(e)}')
            return redirect('book_appointment')
    
    # Get all active specialists ordered by city for better organization
    specialists = EyeSpecialist.objects.filter(is_active=True).order_by('city', 'first_name')
    
    # Get list of unique cities for search suggestions
    cities = EyeSpecialist.objects.filter(is_active=True).values_list('city', flat=True).distinct().order_by('city')
    
    # Get current datetime for template context
    current_datetime = datetime.now()
    
    context = {
        'specialists': specialists,
        'cities': cities,
        'editing': editing_appointment,
        'today': current_datetime.date(),
        'current_time': current_datetime.strftime('%H:%M')
    }
    
    return render(request, 'book_appointment.html', context)

from django.shortcuts import render, redirect
from django.contrib import messages
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone  # Import timezone for today's date

def specialist_dashboard(request):
    if 'user_id' not in request.session or request.session.get('user_type') != 'specialist':
        messages.error(request, 'Please login as a specialist first')
        return redirect('login')
        
    if request.method == 'POST':
        appointment_id = request.POST.get('appointment_id')
        action = request.POST.get('action')
        
        appointment = Appointment.objects.get(id=appointment_id)
        if action == 'confirm':
            appointment.status = 'CONFIRMED'
            # Send confirmation email to patient
            subject = 'Your Eye Appointment is Confirmed'
            message = f'''<!DOCTYPE html>
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
    <div style="background-color: #f8f9fa; padding: 20px; border-radius: 5px; margin-bottom: 20px;">
        <h2 style="color: #2c3e50; margin-bottom: 20px; text-align: center;">Appointment Confirmation</h2>
        
        <p style="font-size: 16px; margin-bottom: 15px;">Dear {appointment.patient.first_name} {appointment.patient.last_name},</p>
        
        <p style="margin-bottom: 20px;">Your appointment has been confirmed with Dr. {appointment.specialist.first_name} {appointment.specialist.last_name}.</p>
        
        <div style="background-color: #ffffff; padding: 15px; border-left: 4px solid #3498db; margin-bottom: 20px;">
            <h3 style="color: #2c3e50; margin-top: 0;">Appointment Details</h3>
            <p style="margin: 5px 0;"><strong>Date:</strong> {appointment.appointment_date}</p>
            <p style="margin: 5px 0;"><strong>Time:</strong> {appointment.appointment_time}</p>
            <p style="margin: 5px 0;"><strong>Location:</strong> {appointment.specialist.clinic_name}</p>
            <p style="margin: 5px 0;"><strong>Address:</strong> {appointment.specialist.address}</p>
        </div>
        
        <div style="background-color: #fff3cd; padding: 10px; border-radius: 4px; margin-bottom: 20px;">
            <p style="color: #856404; margin: 0;">⏰ Please arrive 10 minutes before your scheduled appointment time.</p>
        </div>
        
        <div style="background-color: #d4edda; padding: 10px; border-radius: 4px; margin-bottom: 20px;">
            <p style="color: #155724; margin: 0;">
                If you need to cancel or reschedule, please contact us as soon as possible.
            </p>
        </div>
        
        <div style="text-align: center; margin-top: 30px; padding-top: 20px; border-top: 1px solid #dee2e6;">
            <p style="color: #6c757d; font-size: 14px;">Thank you for choosing SetFrames</p>
            <p style="color: #6c757d; font-size: 12px;">For any queries, please contact our support team</p>
        </div>
    </div>
</body>
</html>'''
            
            send_mail(
                subject,
                "Plain text version of the message",  # Plain text fallback
                settings.DEFAULT_FROM_EMAIL,
                [appointment.patient.email],
                fail_silently=False,
                html_message=message  # HTML version
            )
        elif action == 'cancel':
            appointment.status = 'CANCELLED'
        elif action == 'complete':
            appointment.status = 'COMPLETED'
        appointment.save()
        
        messages.success(request, f'Appointment {action}ed successfully')
        return redirect('specialist_dashboard')
    
    try:
        specialist = EyeSpecialist.objects.get(id=request.session['user_id'])
        appointments = Appointment.objects.filter(specialist=specialist).order_by('appointment_date', 'appointment_time')
        
        # Calculate additional metrics
        total_appointments = appointments.count()
        pending_appointments = appointments.filter(status='PENDING').count()
        today = timezone.localdate()  # Get current date
        todays_appointments = appointments.filter(appointment_date=today).count()
        
        context = {
            'specialist': specialist,
            'appointments': appointments,
            'total_appointments': total_appointments,
            'pending_appointments': pending_appointments,
            'todays_appointments': todays_appointments
        }
        return render(request, 'specialist_dashboard.html', context)
    except EyeSpecialist.DoesNotExist:
        messages.error(request, 'Specialist account not found')
        return redirect('login')
    

@restrict_to_customers
def my_appointments(request):
    if 'user_id' not in request.session or request.session.get('user_type') != 'user':
        messages.error(request, 'Please login to view appointments')
        return redirect('login')
        
    patient = UserDetails.objects.get(id=request.session['user_id'])
    appointments = Appointment.objects.filter(patient=patient).order_by('appointment_date', 'appointment_time')
    
    context = {
        'appointments': appointments
    }
    return render(request, 'my_appointments.html', context)

def edit_appointment(request, appointment_id):
    if 'user_id' not in request.session:
        messages.error(request, 'Please login first')
        return redirect('login')
        
    try:
        appointment = Appointment.objects.get(
            id=appointment_id,
            patient_id=request.session['user_id'],
            status='PENDING'
        )
    except Appointment.DoesNotExist:
        messages.error(request, 'Appointment not found or cannot be edited')
        return redirect('my_appointments')

    if request.method == 'POST':
        new_date = request.POST.get('appointment_date')
        new_time = request.POST.get('appointment_time')
        new_reason = request.POST.get('reason')
        
        try:
            # Convert appointment date and time to datetime for validation
            appointment_datetime = datetime.strptime(
                f"{new_date} {new_time}", 
                "%Y-%m-%d %H:%M"
            )
            current_datetime = datetime.now()

            # Check if appointment datetime is in the past
            if appointment_datetime < current_datetime:
                messages.error(request, 'Cannot book appointments in the past')
                return redirect('book_appointment')

        except ValueError:
            messages.error(request, 'Invalid date or time format')
            return redirect('book_appointment')

        # Check for existing appointments at the same time
        existing_appointment = Appointment.objects.filter(
            specialist=appointment.specialist,
            appointment_date=new_date,
            appointment_time=new_time
        ).exclude(id=appointment_id).exists()
        
        if existing_appointment:
            messages.error(request, 'This time slot is already booked. Please choose another time.')
            return redirect('book_appointment')
        
        # Update appointment
        appointment.appointment_date = new_date
        appointment.appointment_time = new_time
        appointment.reason = new_reason
        appointment.save()
        
        messages.success(request, 'Appointment updated successfully')
        return redirect('my_appointments')
    
    # For GET request, redirect to booking page with edit parameters
    specialists = EyeSpecialist.objects.filter(is_active=True).order_by('city', 'first_name')
    cities = EyeSpecialist.objects.filter(is_active=True).values_list('city', flat=True).distinct().order_by('city')
    current_datetime = datetime.now()
    
    context = {
        'specialists': specialists,
        'cities': cities,
        'editing': appointment,  # Pass the appointment being edited
        'today': current_datetime.date(),
        'current_time': current_datetime.strftime('%H:%M')
    }
    
    return render(request, 'book_appointment.html', context)

from django.http import HttpResponse
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from io import BytesIO
from datetime import datetime, timedelta

def generate_appointment_report(request, report_type):
    if 'user_id' not in request.session or request.session.get('user_type') != 'specialist':
        messages.error(request, 'Please login as a specialist first')
        return redirect('login')

    specialist = EyeSpecialist.objects.get(id=request.session['user_id'])
    
    # Get date range based on report type
    today = datetime.now().date()
    if report_type == 'daily':
        start_date = today
        end_date = today
        title = f"Daily Appointment Report - {today.strftime('%B %d, %Y')}"
    elif report_type == 'weekly':
        start_date = today - timedelta(days=today.weekday())
        end_date = start_date + timedelta(days=6)
        title = f"Weekly Appointment Report ({start_date.strftime('%B %d')} - {end_date.strftime('%B %d, %Y')})"
    elif report_type == 'monthly':
        start_date = today.replace(day=1)
        end_date = (start_date + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        title = f"Monthly Appointment Report - {today.strftime('%B %Y')}"

    # Get appointments for the date range
    appointments = Appointment.objects.filter(
        specialist=specialist,
        appointment_date__range=[start_date, end_date]
    ).order_by('appointment_date', 'appointment_time')

    # Create PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []

    # Add header data
    data = [
        ['Date', 'Time', 'Patient Name', 'Status'],
    ]

    # Add appointment data
    for appointment in appointments:
        data.append([
            appointment.appointment_date.strftime('%Y-%m-%d'),
            appointment.appointment_time.strftime('%H:%M'),
            f"{appointment.patient.first_name} {appointment.patient.last_name}",
            appointment.status
        ])

    # Create table
    table = Table(data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 14),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    
    elements.append(table)
    doc.build(elements)

    # Get PDF value from buffer
    pdf = buffer.getvalue()
    buffer.close()

    # Create response
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{report_type}_report_{today.strftime("%Y%m%d")}.pdf"'
    response.write(pdf)

    return response

from django.http import JsonResponse

@csrf_protect
def cancel_appointment(request):
    if request.method == 'POST':
        appointment_id = request.POST.get('appointment_id')
        try:
            # Get appointment and verify ownership
            appointment = Appointment.objects.get(
                id=appointment_id,
                patient_id=request.session['user_id']
            )
            
            # Check if appointment can be cancelled
            if appointment.status in ['COMPLETED', 'CANCELLED']:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Cannot cancel a completed or already cancelled appointment'
                })
            
            # Cancel the appointment
            appointment.status = 'CANCELLED'
            appointment.save()
            
            return JsonResponse({
                'status': 'success',
                'message': 'Appointment cancelled successfully'
            })
            
        except Appointment.DoesNotExist:
            return JsonResponse({
                'status': 'error',
                'message': 'Appointment not found'
            })
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            })
    
    return JsonResponse({
        'status': 'error',
        'message': 'Invalid request method'
    })

@restrict_to_customers
def add_review(request, order_id, product_id):
    # Retrieve user from session
    try:
        user_id = request.session['user_id']
    except KeyError:
        messages.error(request, "Session expired or not set. Please log in again.")
        return redirect('login')
    
    try:
        up = UserDetails.objects.get(id=int(user_id))
    except UserDetails.DoesNotExist:
        messages.error(request, "Invalid user session.")
        return redirect('login')
    
    if request.method == 'POST':
        try:
            # Get the order for this user and the product
            order = Orders.objects.get(id=order_id, customer=up)
            product = Lense.objects.get(p_id=product_id)  # Changed from id=product_id to p_id=product_id
            
            # Verify that the product is part of the order using the order's cart products
            if not order.cart.cartproduct_set.filter(product=product).exists():
                messages.error(request, "You can only review products you've purchased.")
                return redirect('my-orders')
            
            # Check if the order is completed.
            if order.order_status.lower() != "order completed":
                messages.error(request, "You can only review products from completed orders.")
                return redirect('my-orders')
            
            # Check if a review already exists for this order, product, and user.
            if Review.objects.filter(order=order, product=product, user=up).exists():
                messages.error(request, "You have already reviewed this product for this order.")
                return redirect('my-orders')
            
            # Retrieve rating and comment from POST data.
            rating = int(request.POST.get('rating'))
            comment = request.POST.get('comment')
            
            if not (1 <= rating <= 5):
                messages.error(request, "Rating must be between 1 and 5.")
                return redirect('my-orders')
            
            # Create the review record.
            Review.objects.create(
                product=product,
                user=up,
                rating=rating,
                comment=comment,
                order=order
            )
            
            messages.success(request, "Thank you for your review!")
            return redirect('my-orders')
            
        except (Orders.DoesNotExist, Lense.DoesNotExist):
            messages.error(request, "Invalid order or product.")
            return redirect('my-orders')
    
    return redirect('my-orders')

from django.shortcuts import render
from django.db.models import Count, Avg
from textblob import TextBlob
from .models import Lense

def admin_product_reviews(request):
    filter_option = request.GET.get('filter', 'all')  # default is 'all'

    # Annotate each product with review count and average rating
    products = Lense.objects.all().annotate(
        review_count=Count('reviews'),
        avg_rating=Avg('reviews__rating')
    )
    
    # Apply filters based on the query parameter
    if filter_option == 'top-rated':
        products = products.order_by('-avg_rating')
    elif filter_option == 'most-reviewed':
        products = products.order_by('-review_count')
    elif filter_option == 'top-positive':
        products = products.filter(avg_rating__gte=4).order_by('-avg_rating')
    elif filter_option == 'top-negative':
        products = products.filter(avg_rating__lte=2).order_by('avg_rating')
    else:
        products = products.order_by('p_name')  # default ordering

    # Evaluate the queryset and compute sentiment distribution for each product.
    products = list(products)
    for product in products:
        sentiment_distribution = {"Positive": 0, "Neutral": 0, "Negative": 0}
        # Loop over all reviews for this product using the related name 'reviews'
        for review in product.reviews.all():
            polarity = TextBlob(review.comment).sentiment.polarity
            if polarity > 0.1:
                sentiment = "Positive"
            elif polarity < -0.1:
                sentiment = "Negative"
            else:
                sentiment = "Neutral"
            sentiment_distribution[sentiment] += 1
        product.sentiment_distribution = sentiment_distribution

    context = {
        'products': products,
        'filter_option': filter_option,
    }
    return render(request, 'admin_product_reviews.html', context)

 
from django.db.models import Avg
from textblob import TextBlob
from .models import Lense, Review

def product_reviews(request, id):
    product = get_object_or_404(Lense, pk=id)
    reviews = Review.objects.filter(product=product).order_by('-created_at')
    total_reviews = reviews.count()
    if total_reviews:
        avg_rating = reviews.aggregate(Avg('rating'))['rating__avg']
        avg_rating = round(avg_rating, 1)
    else:
        avg_rating = 0

    # Attach sentiment to each review
    for review in reviews:
        polarity = TextBlob(review.comment).sentiment.polarity
        if polarity > 0.1:
            review.sentiment = "Positive"
        elif polarity < -0.1:
            review.sentiment = "Negative"
        else:
            review.sentiment = "Neutral"

    context = {
        'product': product,
        'reviews': reviews,
        'total_reviews': total_reviews,
        'avg_rating': avg_rating,
    }
    return render(request, 'product_reviews.html', context)


from django.db.models.functions import TruncMonth, TruncWeek, TruncDay, TruncYear
from django.views.generic import TemplateView
from django.http import JsonResponse
from datetime import datetime
from dateutil.relativedelta import relativedelta
from django.db.models import Sum, Count

class SalesAnalysisView(TemplateView):
    template_name = 'sales_analysis.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get date filter parameters
        start_date = self.request.GET.get('start_date')
        end_date = self.request.GET.get('end_date')
        period = self.request.GET.get('period', 'monthly')  # Default to monthly
        category_id = self.request.GET.get('category')
        
        # Set default date range if not specified (last 6 months)
        if not start_date:
            start_date = (datetime.now() - relativedelta(months=6)).strftime('%Y-%m-%d')
        if not end_date:
            end_date = datetime.now().strftime('%Y-%m-%d')
        
        # Filter orders by date range
        orders = Orders.objects.filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
            order_status__in=["order completed", "order on the way", "order processing"]  # Exclude cancelled orders
        )
        
        # Filter by category if provided
        if category_id:
            # Filter through cart products to orders that contain products in this category
            cart_ids = CartProduct.objects.filter(
                product__cat_id=category_id
            ).values_list('cart_id', flat=True).distinct()
            
            orders = orders.filter(cart_id__in=cart_ids)
        
        # Total revenue in the period
        total_revenue = orders.aggregate(total=Sum('total'))['total'] or 0
        
        # Total orders in the period
        total_orders = orders.count()
        
        # Average order value
        avg_order_value = total_revenue / total_orders if total_orders > 0 else 0
        
        # Get all categories for the filter dropdown
        categories = Category.objects.all()
        
        # Time series data based on period
        if period == 'monthly':
            time_series = orders.annotate(
                period=TruncMonth('created_at')
            ).values('period').annotate(
                revenue=Sum('total'),
                orders=Count('id')
            ).order_by('period')

        elif period == 'yearly':
            time_series = orders.annotate(
                period=TruncYear('created_at')
            ).values('period').annotate(
                revenue=Sum('total'),
                orders=Count('id')
            ).order_by('period')

        elif period == 'weekly':
            time_series = orders.annotate(
                period=TruncWeek('created_at')
            ).values('period').annotate(
                revenue=Sum('total'),
                orders=Count('id')
            ).order_by('period')
        else:  # daily
            time_series = orders.annotate(
                period=TruncDay('created_at')
            ).values('period').annotate(
                revenue=Sum('total'),
                orders=Count('id')
            ).order_by('period')
        
        # Top selling products - using Django ORM instead of raw SQL
        top_products = []
        cart_products = CartProduct.objects.filter(
            cart__orders__created_at__date__gte=start_date,
            cart__orders__created_at__date__lte=end_date,
            cart__orders__order_status__in=["order completed", "order on the way", "order processing"]
        )
        
        if category_id:
            cart_products = cart_products.filter(product__cat_id=category_id)
            
        top_products_data = cart_products.values(
            'product__p_id', 
            'product__p_name'
        ).annotate(
            total_quantity=Sum('quantity'),
            total_revenue=Sum('subtotal')
        ).order_by('-total_quantity')[:5]
        
        # Convert to the same format as the previous raw query
        for item in top_products_data:
            top_products.append({
                'p_id': item['product__p_id'],
                'p_name': item['product__p_name'],
                'total_quantity': item['total_quantity'],
                'total_revenue': item['total_revenue']
            })
        
        # Top customers
        top_customers = orders.values(
            'customer__username', 
            'customer__first_name', 
            'customer__last_name'
        ).annotate(
            total_spent=Sum('total'),
            orders_count=Count('id')
        ).order_by('-total_spent')[:5]
        
        # Sales by shape - using Django ORM instead of raw SQL
        sales_by_shape = []
        if not category_id:
            shape_sales = CartProduct.objects.filter(
                cart__orders__created_at__date__gte=start_date,
                cart__orders__created_at__date__lte=end_date,
                cart__orders__order_status__in=["order completed", "order on the way", "order processing"]
            ).values(
                'product__shape'
            ).annotate(
                quantity_sold=Sum('quantity'),
                revenue=Sum('subtotal')
            ).order_by('-revenue')
            
            for item in shape_sales:
                sales_by_shape.append({
                    'shape': item['product__shape'],
                    'quantity_sold': item['quantity_sold'],
                    'revenue': item['revenue']
                })
        
        context.update({
            'start_date': start_date,
            'end_date': end_date,
            'period': period,
            'category_id': category_id,
            'categories': categories,
            'total_revenue': total_revenue,
            'total_orders': total_orders,
            'avg_order_value': avg_order_value,
            'time_series': list(time_series),
            'top_products': top_products,
            'top_customers': list(top_customers),
            'sales_by_shape': sales_by_shape,
            
        })
        
        return context

def sales_chart_data(request):
    """API endpoint for chart data - no authentication required"""
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    period = request.GET.get('period', 'monthly')
    category_id = request.GET.get('category')
    
    if not start_date:
        start_date = (datetime.now() - relativedelta(months=6)).strftime('%Y-%m-%d')
    if not end_date:
        end_date = datetime.now().strftime('%Y-%m-%d')
    
    orders = Orders.objects.filter(
        created_at__date__gte=start_date,
        created_at__date__lte=end_date,
        order_status__in=["order completed", "order on the way", "order processing"]
    )
    
    # Filter by category if provided
    if category_id:
        # We need to filter through cart products to orders that contain products in this category
        cart_ids = CartProduct.objects.filter(
            product__cat_id=category_id
        ).values_list('cart_id', flat=True).distinct()
        
        orders = orders.filter(cart_id__in=cart_ids)
    
    # Time series data
    if period == 'monthly':
        time_series = orders.annotate(
            period=TruncMonth('created_at')
        ).values('period').annotate(
            revenue=Sum('total'),
            orders=Count('id'),
            avg_order_value=Sum('total') / Count('id')  # Added avg order value
        ).order_by('period')
    elif period == 'weekly':
        time_series = orders.annotate(
            period=TruncWeek('created_at')
        ).values('period').annotate(
            revenue=Sum('total'),
            orders=Count('id'),
            avg_order_value=Sum('total') / Count('id')  # Added avg order value
        ).order_by('period')
    else:  # daily
        time_series = orders.annotate(
            period=TruncDay('created_at')
        ).values('period').annotate(
            revenue=Sum('total'),
            orders=Count('id'),
            avg_order_value=Sum('total') / Count('id')  # Added avg order value
        ).order_by('period')
    
    # Shape data for pie chart using Django ORM instead of raw SQL
    shape_data = None
    if not category_id:
        shape_data = {
            'labels': [],
            'data': [],
            'background_colors': []  # Adding colors for better visualization
        }
        
        # Predefined colors for chart
        colors = [
            '#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0', '#9966FF',
            '#FF9F40', '#8AC249', '#EA5F89', '#00D8B6', '#9B19F5'
        ]
        
        shape_sales = CartProduct.objects.filter(
            cart__orders__created_at__date__gte=start_date,
            cart__orders__created_at__date__lte=end_date,
            cart__orders__order_status__in=["order completed", "order on the way", "order processing"]
        ).values(
            'product__shape'
        ).annotate(
            quantity_sold=Sum('quantity')
        ).order_by('-quantity_sold')
        
        for i, item in enumerate(shape_sales):
            if item['product__shape']:  # Add null check
                # Capitalize shape name
                shape_data['labels'].append(item['product__shape'].title())
                shape_data['data'].append(item['quantity_sold'])
                shape_data['background_colors'].append(colors[i % len(colors)])
    
    # Add total metrics
    total_metrics = {
        'total_revenue': float(sum(entry['revenue'] for entry in time_series)),
        'total_orders': sum(entry['orders'] for entry in time_series),
        'avg_order_value': float(
            sum(entry['revenue'] for entry in time_series) / 
            sum(entry['orders'] for entry in time_series)
            if sum(entry['orders'] for entry in time_series) > 0 else 0
        )
    }
    
    chart_data = {
        'labels': [entry['period'].strftime('%Y-%m-%d') for entry in time_series],
        'revenue': [float(entry['revenue']) for entry in time_series],
        'orders': [entry['orders'] for entry in time_series],
        'avg_order_value': [float(entry['avg_order_value']) if entry['avg_order_value'] else 0 for entry in time_series],
        'shape_data': shape_data,
        'total_metrics': total_metrics
    }
    
    return JsonResponse(chart_data)

#specalist views
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

def specialist_appointments(request):
    # Get all specialists for the filter dropdown
    specialists = EyeSpecialist.objects.all()
    
    # Get filter parameters from query string
    specialist_id = request.GET.get('specialist')
    date_filter = request.GET.get('date')
    status_filter = request.GET.get('status')
    
    # Base queryset with prefetch related for optimization
    appointments = Appointment.objects.select_related(
        'patient', 'specialist'
    ).order_by('-appointment_date', '-appointment_time')
    
    # Apply filters if provided
    if specialist_id:
        appointments = appointments.filter(specialist_id=specialist_id)
    if date_filter:
        appointments = appointments.filter(appointment_date=date_filter)
    if status_filter:
        appointments = appointments.filter(status=status_filter)
    
    # Calculate statistics for dashboard cards
    total_appointments = appointments.count()
    confirmed_count = appointments.filter(status='CONFIRMED').count()
    pending_count = appointments.filter(status='PENDING').count()
    cancelled_count = appointments.filter(status='CANCELLED').count()
    
    # Pagination
    page = request.GET.get('page', 1)
    paginator = Paginator(appointments, 10)  # Show 10 appointments per page
    
    try:
        appointments = paginator.page(page)
    except PageNotAnInteger:
        appointments = paginator.page(1)
    except EmptyPage:
        appointments = paginator.page(paginator.num_pages)
    
    context = {
        'appointments': appointments,
        'specialists': specialists,
        'selected_specialist': specialist_id,
        'date_filter': date_filter,
        'status_filter': status_filter,
        'total_appointments': total_appointments,
        'confirmed_count': confirmed_count,
        'pending_count': pending_count,
        'cancelled_count': cancelled_count,
    }
    
    return render(request, 'specialist_appointments.html', context)


    """Handle appointment deletion"""
    try:
        appointment = Appointment.objects.get(id=appointment_id)
        
        # Only allow deletion of future appointments
        if appointment.appointment_date >= timezone.now().date():
            appointment.delete()
            messages.success(request, 'Appointment deleted successfully')
        else:
            messages.error(request, 'Cannot delete past appointments')
            
        return redirect('specialist_appointments')
    except Appointment.DoesNotExist:
        messages.error(request, 'Appointment not found')
        return redirect('specialist_appointments')
    

#query tool
from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """
    Template filter to access dictionary items by key
    Usage: {{ dict|get_item:key }}
    """
    return dictionary.get(key, '')

from django.shortcuts import render
from django.apps import apps
from django.db.models import Q
from .forms import QueryForm
import json

def query_tool(request):
    results = None
    headers = []
    error_message = None
    models_dict = {
        'Category': 'p_app.Category',
        'Seller': 'p_app.Seller',
        'Lense': 'p_app.Lense',
        'UserDetails': 'p_app.UserDetails',
        'cart': 'p_app.cart',
        'CartProduct': 'p_app.CartProduct',
        'Orders': 'p_app.Orders',
        'Wishlist': 'p_app.Wishlist',
        'PurchaseOrder': 'p_app.PurchaseOrder',
        'EyeSpecialist': 'p_app.EyeSpecialist',
        'Appointment': 'p_app.Appointment',
        'Review': 'p_app.Review',
    }
    
    # Define sensitive fields that should be excluded
    sensitive_fields = ['password', 'secret', 'key', 'token', 'passwd']

    if request.method == 'POST':
        form = QueryForm(request.POST)
        if form.is_valid():
            try:
                # Get model
                model_name = form.cleaned_data['model']
                model = apps.get_model(models_dict[model_name])
                
                # Start with all objects
                query = model.objects.all()
                
                # Apply filters if provided
                filter_str = form.cleaned_data.get('filters')
                if filter_str and filter_str.strip():
                    filter_dict = {}
                    filter_parts = filter_str.split(',')
                    for part in filter_parts:
                        if '=' in part:
                            key, value = part.strip().split('=')
                            # Handle numeric values
                            try:
                                value = int(value)
                            except ValueError:
                                try:
                                    value = float(value)
                                except ValueError:
                                    # Keep as string if not a number
                                    pass
                            filter_dict[key] = value
                    query = query.filter(**filter_dict)
                
                # Apply field selection
                fields_str = form.cleaned_data.get('fields')
                if fields_str and fields_str.strip():
                    fields = [field.strip() for field in fields_str.split(',')]
                    # Filter out sensitive fields from the user-specified fields
                    headers = [f for f in fields if not any(sensitive_field in f.lower() for sensitive_field in sensitive_fields)]
                else:
                    # Get all field names from the model except sensitive ones
                    all_fields = [field.name for field in model._meta.fields]
                    headers = [f for f in all_fields if not any(sensitive_field in f.lower() for sensitive_field in sensitive_fields)]
                
                # Apply ordering
                order_by = form.cleaned_data.get('order_by')
                if order_by and order_by.strip():
                    order_fields = [field.strip() for field in order_by.split(',')]
                    query = query.order_by(*order_fields)
                
                # Apply limit
                limit = form.cleaned_data.get('limit')
                if limit:
                    query = query[:limit]
                
                # Execute query and prepare results
                results_data = []
                for item in query:
                    row_data = []
                    for header in headers:
                        try:
                            if '__' in header:
                                parts = header.split('__')
                                value = item
                                for part in parts:
                                    value = getattr(value, part)
                            else:
                                value = getattr(item, header)
                            
                            row_data.append(str(value))
                        except (AttributeError, ValueError):
                            row_data.append("N/A")
                    results_data.append(row_data)
                
                results = results_data
                
            except Exception as e:
                error_message = f"Error executing query: {str(e)}"
                
    else:
        form = QueryForm()
        
    return render(request, 'query_tool.html', {
        'form': form,
        'results': results,
        'headers': headers,
        'error_message': error_message
    })


from django.core.mail import send_mail
from django.utils.crypto import get_random_string
import random

def send_delete_account_otp(request):
    """Send OTP for account deletion verification"""
    if 'user_id' not in request.session:
        return JsonResponse({'status': 'error', 'message': 'You must be logged in'})
    
    try:
        user = UserDetails.objects.get(id=request.session['user_id'])
        
        # Generate a 6-digit OTP
        otp = ''.join([str(random.randint(0, 9)) for _ in range(6)])
        
        # Store OTP in session with expiration time (15 minutes)
        request.session['delete_account_otp'] = otp
        request.session['delete_account_otp_expires'] = (timezone.now() + timezone.timedelta(minutes=15)).timestamp()
        
        # Send email with OTP
        subject = 'Account Deletion Verification'
        html_message = f'''
        <!DOCTYPE html>
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background-color: #f8f9fa; padding: 20px; border-radius: 5px; margin-bottom: 20px;">
                <h2 style="color: #dc3545; margin-bottom: 20px; text-align: center;">Account Deletion Request</h2>
                
                <p style="font-size: 16px; margin-bottom: 15px;">Dear {user.first_name} {user.last_name},</p>
                
                <p style="margin-bottom: 20px;">We received a request to delete your SetFrames account. To verify this request, please use the following one-time password (OTP):</p>
                
                <div style="background-color: #ffffff; padding: 15px; border-left: 4px solid #dc3545; margin-bottom: 20px; text-align: center;">
                    <h1 style="margin: 5px 0; color: #dc3545; letter-spacing: 5px;">{otp}</h1>
                </div>
                
                <p style="margin-bottom: 20px;">This code is valid for 15 minutes only.</p>
                
                <div style="background-color: #fff3cd; padding: 10px; border-radius: 4px; margin-bottom: 20px;">
                    <p style="color: #856404; margin: 0;"><strong>Warning:</strong> Account deletion is permanent. All your data will be permanently removed.</p>
                </div>
                
                <p style="margin-bottom: 20px;">If you didn't request to delete your account, please ignore this email and secure your account by changing your password.</p>
                
                <div style="text-align: center; margin-top: 30px; padding-top: 20px; border-top: 1px solid #dee2e6;">
                    <p style="color: #6c757d; font-size: 14px;">The SetFrames Team</p>
                    <p style="color: #6c757d; font-size: 12px;">This is an automated message, please do not reply.</p>
                </div>
            </div>
        </body>
        </html>
        '''
        
        send_mail(
            subject,
            f"Your OTP for account deletion is: {otp}. This code is valid for 15 minutes only.",  # Plain text version
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
            html_message=html_message
        )
        
        return JsonResponse({'status': 'success', 'message': 'OTP sent to your email'})
    
    except UserDetails.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'User not found'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': f'Error sending OTP: {str(e)}'})

def verify_delete_account_otp(request):
    """Verify OTP and anonymize user account"""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid request method'})
    
    if 'user_id' not in request.session:
        return JsonResponse({'status': 'error', 'message': 'You must be logged in'})
    
    try:
        user_id = request.session['user_id']
        user = UserDetails.objects.get(id=user_id)
        provided_otp = request.POST.get('otp', '')
        
        # Check if OTP exists in session
        if 'delete_account_otp' not in request.session:
            return JsonResponse({'status': 'error', 'message': 'No active OTP found. Please request a new one.'})
        
        stored_otp = request.session['delete_account_otp']
        expiry_time = request.session['delete_account_otp_expires']
        
        # Check if OTP has expired
        if timezone.now().timestamp() > expiry_time:
            # Clean up session variables
            del request.session['delete_account_otp']
            del request.session['delete_account_otp_expires']
            return JsonResponse({'status': 'error', 'message': 'OTP has expired. Please request a new one.'})
        
        # Check if OTP matches
        if provided_otp != stored_otp:
            return JsonResponse({'status': 'error', 'message': 'Invalid OTP. Please try again.'})
        
        # OTP is valid, proceed with account anonymization
        with transaction.atomic():
             # Delete appointments for this patient
            Appointment.objects.filter(patient_id=user_id).delete()
            # Generate a random string to make the email unique but anonymous
            random_suffix = get_random_string(8)
            
            # Anonymize user's personal data
            user.first_name = "Deleted"
            user.last_name = "User"
            user.email = f"deleted_{random_suffix}@anonymous.com"
            user.mobile_phone = f"0000000000"  # 10 zeros
            user.password = get_random_string(20)  # Random password no one knows
            
            # Set a flag to indicate this account is anonymized
            # (assuming you have this field, add it if you don't)
            if hasattr(user, 'is_active'):
                user.is_active = False
            
            # Save the anonymized user
            user.save()
        
        # Clear session
        request.session.flush()
        
        return JsonResponse({'status': 'success', 'message': 'Your account has been deactivated and your personal information has been removed'})
    
    except UserDetails.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'User not found'})
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Account anonymization error: {error_details}")
        return JsonResponse({'status': 'error', 'message': f'Error anonymizing account: {str(e)}'})
    
# Modify the user_profile view to include the account deletion functionality
def user_profile(request, user_id):
    """
    Display and update user profile information including order history with validation
    """
    try:
        # Get the user profile based on the ID
        user = UserDetails.objects.get(id=user_id)
        
        # Check if the logged-in user is accessing their own profile
        if 'user_id' not in request.session or request.session['user_id'] != user.id:
            return HttpResponseForbidden("You don't have permission to view this profile")
        
        # Get user's order information
        orders = Orders.objects.filter(customer=user).order_by('-created_at')
        orders_count = orders.count()
        recent_orders = orders[:5]  # Get 5 most recent orders
        
        # Format recent orders with additional info
        formatted_recent_orders = []
        for order in recent_orders:
            status_colors = {
                "order received": "info",
                "order processing": "primary",
                "order on the way": "warning",
                "order completed": "success",
                "order cancelled": "danger"
            }
            status_color = status_colors.get(order.order_status.lower(), "secondary")
            
            formatted_recent_orders.append({
                'id': order.id,
                'created_at': order.created_at,
                'total': order.total,
                'status': order.order_status,
                'status_color': status_color,
                'products': [{'name': cp.product.p_name, 'quantity': cp.quantity} 
                             for cp in order.cart.cartproduct_set.all()]
            })
        
        # Get recent activity
        if orders.exists():
            recent_activity = orders.first().created_at.strftime("%b %d, %Y")
        else:
            recent_activity = None
            
        if request.method == 'POST':
            # Check if this is a delete account request
            if 'delete_account_confirm' in request.POST:
                # This is just a form submission to show the OTP modal
                # The actual deletion happens in verify_delete_account_otp view
                # We'll handle this with JavaScript in the template
                pass
            else:
                # Regular profile update process
                first_name = request.POST.get('first_name', '').strip()
                last_name = request.POST.get('last_name', '').strip()
                email = request.POST.get('email', '').strip()
                mobile_phone = request.POST.get('mobile_phone', '').strip()
                new_password = request.POST.get('new_password', '')
                confirm_password = request.POST.get('confirm_password', '')
                
                # Validation flags
                has_error = False
                
                # Validation code (unchanged)...
                if not first_name or not last_name:
                    messages.error(request, 'First name and last name are required')
                    has_error = True
                elif not all(c.isalnum() or c.isspace() for c in first_name + last_name):
                    messages.error(request, 'Names should only contain letters, numbers, and spaces')
                    has_error = True
                
                # Validate email (required, format)
                import re
                email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
                if not email:
                    messages.error(request, 'Email is required')
                    has_error = True
                elif not re.match(email_pattern, email):
                    messages.error(request, 'Please enter a valid email address')
                    has_error = True
                elif email != user.email:
                    # Check if email is already taken by another user
                    if UserDetails.objects.filter(email=email).exclude(id=user.id).exists():
                        messages.error(request, 'This email is already registered to another account')
                        has_error = True
                
                # Validate mobile phone (required, format)
                phone_pattern = r'^\d{10}$'  # Assuming 10-digit phone numbers
                if not mobile_phone:
                    messages.error(request, 'Mobile phone number is required')
                    has_error = True
                elif not re.match(phone_pattern, mobile_phone):
                    messages.error(request, 'Please enter a valid 10-digit phone number')
                    has_error = True
                elif mobile_phone != user.mobile_phone:
                    # Check if phone is already taken by another user
                    if UserDetails.objects.filter(mobile_phone=mobile_phone).exclude(id=user.id).exists():
                        messages.error(request, 'This phone number is already registered to another account')
                        has_error = True
                
                # Validate password if provided
                if new_password:
                    # Check password length
                    if len(new_password) < 8:
                        messages.error(request, 'Password must be at least 8 characters long')
                        has_error = True
                    # Check password complexity
                    elif not (any(c.islower() for c in new_password) and 
                             any(c.isupper() for c in new_password) and 
                             any(c.isdigit() for c in new_password)):
                        messages.error(request, 'Password must contain at least one lowercase letter, one uppercase letter, and one number')
                        has_error = True
                    # Check if passwords match
                    elif new_password != confirm_password:
                        messages.error(request, 'Passwords do not match')
                        has_error = True
                
                
                # If validation passed, update the user profile
                if not has_error:
                    user.first_name = first_name
                    user.last_name = last_name
                    user.email = email
                    user.mobile_phone = mobile_phone
                    
                    # Update password if provided
                    if new_password:
                        user.password = new_password  # Note: In a real app, you should hash this
                    
                    # Update profile picture if provided
                    if 'profile_picture' in request.FILES:
                        user.profile_picture = request.FILES['profile_picture']
                        
                    user.save()
                    messages.success(request, 'Profile updated successfully')
                    return redirect('user_profile', user_id=user.id)
        
        # Render the profile page with context data
        return render(request, 'user_profile.html', {
            'user': user,
            'orders_count': orders_count,
            'recent_orders': formatted_recent_orders,
            'recent_activity': recent_activity
        })
    
    except UserDetails.DoesNotExist:
        messages.error(request, 'User not found')
        return redirect('home')  # Redirect to home page if user doesn't exist
    

def patient_details(request, appointment_id):
    """
    View for specialists to see detailed information about patients associated with their appointments
    """
    if 'user_id' not in request.session or request.session.get('user_type') != 'specialist':
        messages.error(request, 'Please login as a specialist first')
        return redirect('login')
    
    try:
        # Get the specialist and appointment, ensuring the appointment belongs to this specialist
        specialist = EyeSpecialist.objects.get(id=request.session['user_id'])
        appointment = Appointment.objects.select_related('patient').get(
            id=appointment_id,
            specialist=specialist
        )
        
        # Get patient details
        patient = appointment.patient
        
        # Get patient's appointment history with this specialist
        appointment_history = Appointment.objects.filter(
            patient=patient,
            specialist=specialist
        ).exclude(id=appointment_id).order_by('-appointment_date', '-appointment_time')
        
        # # Get patient's order history for eyewear
        # order_history = Orders.objects.filter(
        #     customer=patient
        # ).order_by('-created_at')
        
        # # Get details of purchased lenses
        # purchased_products = []
        # for order in order_history:
        #     for cart_product in order.cart.cartproduct_set.all():
        #         lens = cart_product.product
        #         purchased_products.append({
        #             'name': lens.p_name,
        #             'shape': lens.shape,
        #             'quantity': cart_product.quantity,
        #             'order_date': order.created_at,
        #             'order_status': order.order_status
        #         })
        
        context = {
            'specialist': specialist,
            'appointment': appointment,
            'patient': patient,
            'appointment_history': appointment_history,
        #     'order_history': order_history,
        #     'purchased_products': purchased_products
         }
        
        return render(request, 'patient_details.html', context)
    
    except EyeSpecialist.DoesNotExist:
        messages.error(request, 'Specialist account not found')
        return redirect('login')
    except Appointment.DoesNotExist:
        messages.error(request, 'Appointment not found or access denied')
        return redirect('specialist_dashboard')
    

#chat bot
from django.shortcuts import render
from django.http import JsonResponse
import google.generativeai as genai
import os
import json
from .models import Lense, Review, EyeSpecialist, Category
from django.db.models import Avg, Count, F, Q, Max, Min, Sum
from django.views.decorators.csrf import csrf_exempt

def chatbot(request):
    """View for displaying and handling the chatbot interface"""
    if request.method == "POST" and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        user_message = request.POST.get('message', '').strip()
        
        if not user_message:
            return JsonResponse({'error': 'Please enter a message'})
        
        try:
            # Get user session info if available for personalization
            user_id = request.session.get('user_id')
            user_type = request.session.get('user_type')
            
            # Prepare chatbot response using Gemini API
            response_data = generate_chatbot_response(user_message, user_id, user_type)
            if isinstance(response_data, dict):
                return JsonResponse(response_data)
            else:
                return JsonResponse({'response': response_data})
        except Exception as e:
            print(f"Chatbot error: {str(e)}")  # Add logging for debugging
            return JsonResponse({'error': f"Error processing your request: {str(e)}"})
    
    # For GET requests, just render the chatbot interface
    context = {
        'initial_message': "Hello! I'm your SetFrames eyewear assistant. How can I help you today?"
    }
    return render(request, 'chatbot.html', context)

# ...existing code...

def generate_chatbot_response(user_message, user_id=None, user_type=None):
    """Generate response using Gemini API enriched with database lookups"""
    # Check if API key exists
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return {'response': "ERROR: Gemini API key not found. Please set the GEMINI_API_KEY environment variable."}
    
    # Configure Gemini API
    genai.configure(api_key=api_key)
    
    # Import timezone for date comparisons
    from django.utils import timezone
    
    # Check if the query is about frames, lenses, reviews, or specialists
    user_message_lower = user_message.lower()
    
    # Initialize context information
    db_context = ""
    personalized_context = ""
    query_type = "general"
    
    # Personalize if user is logged in
    if user_id:
        try:
            if user_type == 'user':
                user = UserDetails.objects.get(id=user_id)
                personalized_context = f"Customer: {user.first_name} {user.last_name}\n"
                
                # Check if user is asking about orders
                if any(word in user_message_lower for word in ['my order', 'my orders', 'order status', 'purchase', 'i bought', 'i ordered',
                                                                'track order', 'order tracking', 'order history', 'past orders',
                                                                'order details', 'shipping status', 'delivery status', 'package',
                                                                'where is my order', 'when will my order', 'order number', 'order id',
                                                                'bought', 'purchased', 'recent order', 'last order', 'check order',
                                                                'order confirmation', 'receipt', 'invoice', 'transaction', 
                                                                'what did i buy', 'what i ordered', 'items i ordered',
                                                                'glasses i ordered', 'frames i ordered', 'eyewear i ordered',
                                                                'order placed', 'order received', 'order processed',
                                                                'show me my orders', 'view orders', 'check my purchases', 'recently ordered']):
                    orders = Orders.objects.filter(customer=user).order_by('-created_at')
                    if orders.exists():
                        personalized_context += "\nOrder History:\n"
                        for i, order in enumerate(orders[:5], 1):  # Show last 5 orders
                            personalized_context += f"\nOrder #{order.id} - {order.created_at.strftime('%Y-%m-%d')}\n"
                            personalized_context += f"Status: {order.order_status}\n"
                            personalized_context += f"Total: ₹{order.total}\n"
                            personalized_context += "Products:\n"
                            
                            for cart_product in order.cart.cartproduct_set.all():
                                personalized_context += f"- {cart_product.quantity}x {cart_product.product.p_name} (₹{cart_product.rate} each)\n"
                            
                            # Add a view link for the order
                            personalized_context += f"[View Order Details: <a href='/my-orders'>Order #{order.id}</a>]\n"
                            
                            if i < min(5, orders.count()):
                                personalized_context += "----------\n"
                        
                        # Add link to view all orders
                        if orders.count() > 5:
                            personalized_context += f"\n[View all {orders.count()} orders: <a href='/my-orders'>My Orders</a>]\n"
                    else:
                        personalized_context += "\nYou don't have any orders yet.\n"
                        personalized_context += "[Start shopping: <a href='/shop'>Shop Now</a>]\n"

                # Improved appointment handling for the chatbot

                elif any(word in user_message_lower for word in[
                                # Simple appointment terms
                                'appointment', 'appointments', 'eye exam', 'eye test', 'check-up', 'checkup', 
                                'consultation', 'booking', 'book', 'booked', 'scheduled', 'schedule', 
                                # Questions about appointments
                                'when is my', 'do i have', 'next appointment', 'upcoming', 'eye doctor',
                                # Time references for appointments
                                'visit', 'session', 'meeting', 'exam', 'examination',
                                # Actions related to appointments
                                'reschedule', 'cancel', 'change', 'postpone', 'confirm',
                                # Combinations with possessives
                                'my next', 'my eye', 'have an appointment'
                            ]):
                    try:
                        # Get user's appointments with proper error handling
                        appointments = Appointment.objects.filter(patient=user).order_by('-appointment_date')
                        
                        if appointments.exists():
                            personalized_context += "\nYour Appointment Information:\n"
                            
                            # Show upcoming appointments first
                            try:
                                upcoming = appointments.filter(appointment_date__gte=timezone.now().date())
                                if upcoming.exists():
                                    personalized_context += "\n--- Upcoming Appointments ---\n"
                                    for appt in upcoming:
                                        try:
                                            # Format date safely
                                            appt_date = appt.appointment_date.strftime('%B %d, %Y') if hasattr(appt.appointment_date, 'strftime') else str(appt.appointment_date)
                                            
                                            # Format time safely
                                            appt_time = appt.appointment_time.strftime('%I:%M %p') if hasattr(appt.appointment_time, 'strftime') else str(appt.appointment_time)
                                            
                                            personalized_context += f"\nAppointment on {appt_date}\n"
                                            personalized_context += f"Time: {appt_time}\n"
                                            
                                            # Get status display with proper error handling
                                            if hasattr(appt, 'get_status_display') and callable(getattr(appt, 'get_status_display')):
                                                status_display = appt.get_status_display()
                                            else:
                                                status_display = appt.status
                                            personalized_context += f"Status: {status_display}\n"
                                            
                                            # Add specialist information with proper checks
                                            if hasattr(appt, 'specialist') and appt.specialist:
                                                specialist_name = f"Dr. {appt.specialist.first_name} {appt.specialist.last_name}"
                                                personalized_context += f"With: {specialist_name}\n"
                                                
                                                if hasattr(appt.specialist, 'clinic_name'):
                                                    personalized_context += f"At: {appt.specialist.clinic_name}"
                                                    if hasattr(appt.specialist, 'city'):
                                                        personalized_context += f", {appt.specialist.city}"
                                                    personalized_context += "\n"
                                            
                                            if hasattr(appt, 'reason') and appt.reason:
                                                personalized_context += f"Reason: {appt.reason}\n"
                                            
                                            # Add action links based on status
                                            if appt.status == 'PENDING':
                                                personalized_context += f"[Manage Appointment: <a href='/my-appointments'>Reschedule or Cancel</a>]\n"
                                            elif appt.status == 'CONFIRMED':
                                                personalized_context += f"[Appointment Details: <a href='/my-appointments'>View Details</a>]\n"
                                        except Exception as e:
                                            print(f"Error processing appointment: {str(e)}")
                                            continue
                            except Exception as e:
                                print(f"Error processing upcoming appointments: {str(e)}")
                            
                            # Show past appointments with separate error handling
                            try:
                                past = appointments.filter(appointment_date__lt=timezone.now().date())
                                if past.exists():
                                    personalized_context += "\n--- Past Appointments ---\n"
                                    for appt in past[:3]:
                                        try:
                                            appt_date = appt.appointment_date.strftime('%B %d, %Y') if hasattr(appt.appointment_date, 'strftime') else str(appt.appointment_date)
                                            
                                            personalized_context += f"\nDate: {appt_date}\n"
                                            
                                            if hasattr(appt, 'specialist') and appt.specialist:
                                                specialist_name = f"Dr. {appt.specialist.first_name}"
                                                personalized_context += f"With: {specialist_name}\n"
                                            
                                            if hasattr(appt, 'get_status_display') and callable(getattr(appt, 'get_status_display')):
                                                status_display = appt.get_status_display()
                                            else:
                                                status_display = appt.status
                                            personalized_context += f"Status: {status_display}\n"
                                        except Exception as e:
                                            print(f"Error processing past appointment: {str(e)}")
                                            continue
                            except Exception as e:
                                print(f"Error processing past appointments: {str(e)}")
                            
                            # Add link to manage appointments
                            personalized_context += f"\n[Manage your appointments: <a href='/my-appointments'>My Appointments</a>]\n"
                        else:
                            personalized_context += "\nYou don't have any appointments scheduled.\n"
                            personalized_context += "[Book an appointment: <a href='/book-appointment'>Book Now</a>]\n"
                    except Exception as e:
                        print(f"Overall appointment retrieval error: {str(e)}")
                        personalized_context += "\nI'm having trouble retrieving your appointment information. Please try again later or check your account directly.\n"
                

                else:
                    # Check if customer has previous orders to provide better recommendations
                    orders = Orders.objects.filter(customer=user).order_by('-created_at')
                    if orders.exists():
                        past_purchases = []
                        for order in orders[:3]:  # Get last 3 orders
                            for cart_product in order.cart.cartproduct_set.all():
                                past_purchases.append({
                                    'name': cart_product.product.p_name,
                                    'shape': cart_product.product.shape,
                                    'category': cart_product.product.cat.name if cart_product.product.cat else 'Unknown'
                                })
                        
                        if past_purchases:
                            personalized_context += "Past purchases:\n"
                            for item in past_purchases[:5]:  # Limit to 5 items
                                personalized_context += f"- {item['name']} ({item['shape']} shape, {item['category']} category)\n"
        except Exception as e:
            print(f"Error getting personalization data: {str(e)}")
    
    # Define common face shapes and their ideal frame matches
    face_shape_recommendations = {
        'oval': ['square', 'rectangle', 'aviator', 'geometric', 'wayfarer'],
        'round': ['rectangular', 'square', 'geometric', 'aviator', 'angular'],
        'square': ['round', 'oval', 'aviator', 'rimless', 'cat-eye'],
        'rectangle': ['round', 'oval', 'geometric', 'oversized'],
        'heart': ['oval', 'round', 'square', 'rimless', 'bottom-heavy'],
        'diamond': ['oval', 'round', 'geometric', 'cat-eye', 'rimless']
    }
    
    # Enhanced query classification using common patterns
    frame_related_terms = ['frame', 'lens', 'eyewear', 'glasses', 'shape', 'prescription', 'sunglasses', 'reading']
    review_related_terms = ['review', 'rating', 'feedback', 'best', 'top rated', 'recommend', 'opinion', 'popular']
    specialist_related_terms = ['specialist', 'doctor', 'optometrist', 'appointment', 'eye exam', 'consultation', 'clinic']
    shipping_related_terms = ['shipping', 'delivery', 'order status', 'tracking', 'shipment', 'arrive', 'when will']
    return_policy_terms = ['return', 'refund', 'exchange', 'warranty', 'guarantee', 'damaged', 'broken']
    pricing_related_terms = ['price', 'cost', 'discount', 'offer', 'sale', 'promotion', 'coupon', 'cheapest', 'expensive']
    
    # Extract potential face shapes from the query
    mentioned_face_shapes = []
    for shape in face_shape_recommendations.keys():
        if shape in user_message_lower:
            mentioned_face_shapes.append(shape)
    
    # Check primary query type - prioritize by relevance and specificity
    if any(word in user_message_lower for word in frame_related_terms):
        query_type = "frame_info"
    elif any(word in user_message_lower for word in review_related_terms):
        query_type = "review_info"
    elif any(word in user_message_lower for word in specialist_related_terms):
        query_type = "specialist_info"
    elif any(word in user_message_lower for word in shipping_related_terms):
        query_type = "shipping_info"
    elif any(word in user_message_lower for word in return_policy_terms):
        query_type = "return_policy"
    elif any(word in user_message_lower for word in pricing_related_terms):
        query_type = "pricing_info"
    
    # Extract data based on query type
    if query_type == "frame_info":
        # Extract possible frame shape or name from query
        possible_shapes = ['oval', 'round', 'square', 'rectangle', 'aviator', 'geometric', 'cat-eye', 'wayfarer']
        mentioned_shapes = [shape for shape in possible_shapes if shape in user_message_lower]
        
        # Process specific searches by product name
        product_name_search = None
        if "looking for" in user_message_lower or "find" in user_message_lower:
            # Extract potential product names using basic NLP
            words = user_message.split()
            for i in range(len(words)):
                if words[i].lower() in ["called", "named", "model", "style", "specific", "find", "looking"]:
                    if i < len(words) - 2:
                        potential_name = " ".join(words[i+1:i+3])
                        # Search for products with this name fragment
                        matching_products = Lense.objects.filter(p_name__icontains=potential_name)
                        if matching_products.exists():
                            product_name_search = potential_name
                            db_context += f"Found products matching '{potential_name}':\n"
                            for product in matching_products[:3]:
                                # Add product ID and link indicator
                                db_context += f"- {product.p_name}: {product.shape} shape, ₹{product.p_price} [Product ID: {product.p_id}]\n"
        
        # If face shape is mentioned but no frame shape, recommend frames for that face shape
        if mentioned_face_shapes and not mentioned_shapes and not product_name_search:
            db_context += f"For your {mentioned_face_shapes[0]} face shape, I recommend these frame styles:\n"
            recommended_frame_shapes = face_shape_recommendations.get(mentioned_face_shapes[0], [])
            
            # Get lenses with the recommended shapes
            lenses = Lense.objects.filter(
                shape__in=recommended_frame_shapes
            ).annotate(
                avg_rating=Avg('reviews__rating')
            ).order_by('-avg_rating')[:5]
            
            if lenses.exists():
                db_context += "Here are some specific frames that would suit your face shape:\n"
                for lens in lenses:
                    rating = lens.avg_rating if lens.avg_rating else "No ratings yet"
                    rating_display = f"{rating:.1f}/5" if isinstance(rating, float) else rating
                    category = lens.cat.name if lens.cat else "Standard"
                    # Add product ID and link indicator
                    db_context += f"- {lens.p_name}: {lens.shape} shape, Category: {category}, ₹{lens.p_price}, Rating: {rating_display} [Product ID: {lens.p_id}]\n"
            else:
                db_context += "Recommended styles include: " + ", ".join(recommended_frame_shapes)
        else:
            # Build optimized query to search for lenses
            lens_query = Lense.objects.select_related('cat').annotate(avg_rating=Avg('reviews__rating'))
            
            # Apply filters based on user query
            filters = Q()
            
            # Filter by shape if mentioned
            if mentioned_shapes:
                filters |= Q(shape__in=mentioned_shapes)
            
            # Check for price indicators
            if any(word in user_message_lower for word in ['cheap', 'affordable', 'inexpensive', 'budget']):
                filters &= Q(p_price__lte=100)  # Arbitrary threshold for "cheap"
            elif any(word in user_message_lower for word in ['expensive', 'premium', 'luxury', 'high-end']):
                filters &= Q(p_price__gte=150)  # Arbitrary threshold for "expensive"
            
            # Check for material preferences
            for material in ['metal', 'plastic', 'titanium', 'acetate']:
                if material in user_message_lower:
                    # Assuming we store material information in the description
                    filters &= Q(p_desc__icontains=material)
            
            # Check for color preferences
            for color in ['black', 'brown', 'blue', 'red', 'gold', 'silver', 'tortoise']:
                if color in user_message_lower:
                    # Assuming we store color information in the description
                    filters &= Q(p_desc__icontains=color)
            
            # Check for category indicators
            for category_keyword in ['sun', 'reading', 'prescription']:
                if category_keyword in user_message_lower:
                    filters &= Q(cat__name__icontains=category_keyword)
            
            # Apply all filters if any exist
            if filters:
                lens_query = lens_query.filter(filters)
            
            # Get top rated or recent lenses with optimized queries
            top_lenses = lens_query.order_by('-avg_rating')[:4]
            
            # Add lens data to context
            if top_lenses.exists():
                db_context += "Here are some eyewear frames that match your criteria:\n\n"
                
                for lens in top_lenses:
                    category_name = lens.cat.name if lens.cat else "General"
                    rating = lens.avg_rating if lens.avg_rating else "No ratings yet"
                    rating_display = f"{rating:.1f}/5" if isinstance(rating, float) else rating
                    
                    # Add product ID with link format
                    db_context += f"- <a href='/view-product/{lens.p_id}/'>{lens.p_name}</a>: {lens.shape} shape, Category: {category_name}\n"
                    db_context += f"  Price: ₹{lens.p_price}, Rating: {rating_display} [Product ID: {lens.p_id}]\n"
                    db_context += f"  Description: {lens.p_desc[:100]}...\n\n"
            elif not product_name_search:  # Only show popular items if no specific product was searched
                # If no specific matches, get most popular frames
                popular_lenses = Lense.objects.annotate(
                    review_count=Count('reviews')
                ).order_by('-review_count')[:4]
                
                if popular_lenses.exists():
                    db_context += "I couldn't find exact matches, but here are our popular frames:\n\n"
                    for lens in popular_lenses:
                        # Add product ID with link format
                        db_context += f"- {lens.p_name}: {lens.shape} shape, ₹{lens.p_price} [Product ID: {lens.p_id}]\n"
    
    # Check for review related queries with improved aggregation
    elif query_type == "review_info":
        # Try to identify if user is asking about a specific product
        specific_product = None
        words = user_message.split()
        
        # Look for product mentions
        for i in range(len(words)-1):
            two_word_phrase = words[i] + " " + words[i+1]
            matching_products = Lense.objects.filter(
                Q(p_name__icontains=words[i]) | Q(p_name__icontains=two_word_phrase)
            )
            if matching_products.exists():
                specific_product = matching_products.first()
                break
        
        if specific_product:
            # Get reviews for the specific product
            reviews = Review.objects.filter(product=specific_product).order_by('-rating')
            review_count = reviews.count()
            
            if review_count > 0:
                avg_rating = reviews.aggregate(Avg('rating'))['rating__avg']
                # Include product ID and link
                db_context += f"Reviews for {specific_product.p_name} ({specific_product.shape} shape) [Product ID: {specific_product.p_id}]:\n"
                db_context += f"View product details: <a href='/view-product/{specific_product.p_id}/'>Click here</a>\n"
                db_context += f"Average rating: {avg_rating:.1f}/5 from {review_count} reviews\n\n"
                
                # Show some sample reviews
                positive_reviews = reviews.filter(rating__gte=4)[:2]
                critical_reviews = reviews.filter(rating__lte=3)[:1]
                
                if positive_reviews:
                    db_context += "What customers like:\n"
                    for review in positive_reviews:
                        db_context += f"- \"{review.comment[:100]}...\"\n"
                
                if critical_reviews:
                    db_context += "\nSome concerns:\n"
                    for review in critical_reviews:
                        db_context += f"- \"{review.comment[:100]}...\"\n"
            else:
                db_context += f"No reviews yet for {specific_product.p_name}. [Product ID: {specific_product.p_id}]"
        else:
            # Get reviews with shape information and optimize the query
            top_reviewed = Lense.objects.annotate(
                avg_rating=Avg('reviews__rating'),
                review_count=Count('reviews')
            ).filter(
                review_count__gt=0  # Only include items with reviews
            ).order_by('-avg_rating')[:5]
            
            if top_reviewed:
                db_context += "Here are our top-rated eyewear frames based on customer reviews:\n\n"
                
                for product in top_reviewed:
                    # Get a sample of positive reviews for this product
                    positive_reviews = Review.objects.filter(
                        product=product,
                        rating__gte=4  # 4 stars or higher
                    ).order_by('-created_at')[:1]
                    
                    # Include product ID and link format
                    db_context += f"- {product.p_name} ({product.shape} shape): " \
                                f"{product.avg_rating:.1f}/5 stars from {product.review_count} reviews\n" \
                                f"  [View details: <a href='/view-product/{product.p_id}/'>Product ID: {product.p_id}</a>]\n"
                    
                    if positive_reviews:
                        db_context += f"  Sample review: \"{positive_reviews[0].comment[:100]}...\"\n"

                     # Check for specialist related queries with improved filtering
    elif any(word in user_message_lower for word in ['specialist', 'doctor', 'optometrist', 'appointment', 'eye exam']):
        # Check for location-specific queries
        location_mentioned = None
        specialists_query = EyeSpecialist.objects.filter(is_active=True)
        
        # Extract potential city names from the query
        cities = EyeSpecialist.objects.values_list('city', flat=True).distinct()
        for city in cities:
            if city.lower() in user_message_lower:
                location_mentioned = city
                specialists_query = specialists_query.filter(city__iexact=city)
        
        specialists = specialists_query.order_by('city', 'first_name')[:5]
        
        if specialists:
            if location_mentioned:
                db_context += f"Here are our eye specialists in {location_mentioned}:\n\n"
            else:
                db_context += "Here are some of our eye specialists:\n\n"
                
            for specialist in specialists:
                db_context += f"- Dr. {specialist.first_name} {specialist.last_name}\n" \
                             f"  Clinic: {specialist.clinic_name}\n" \
                             f"  Location: {specialist.city}, {specialist.state}\n" \
                             f"  [Book Now: <a href='/book-appointment'>Book Now</a>]\n"\
                             f"  Specializes in: Eye examinations and prescriptions\n\n"
            
            db_context += "You can book an appointment with any of our specialists through our website's 'Book Appointment' feature.\n"

    # Rest of your existing code...
    # ...existing code...

    # Add to system instruction for formatting
    system_instruction = """
    You are a helpful eyewear shopping assistant for SetFrames, an online eyewear store.
    You help customers find suitable eyewear based on face shape, style preferences, and vision needs.
    
    Key product knowledge:
    - We offer various frame shapes: oval, round, square, rectangle, aviator, geometric, cat-eye, wayfarer
    - Different face shapes suit different frames: 
      * Oval faces: versatile, can wear most frame styles
      * Round faces: angular frames like square, rectangular, and geometric add definition
      * Square faces: round and oval frames soften sharp angles
      * Heart-shaped faces: frames wider at the bottom balance the face
      * Diamond faces: oval, rimless, and cat-eye frames complement cheekbones
    
    Product lineup:
    - Prescription eyeglasses (single vision, progressive, bifocal)
    - Reading glasses (various magnifications)
    - Sunglasses (polarized and non-polarized options)
    - Computer glasses with blue light filtering
    - Price ranges from affordable (₹50-100) to premium (₹150+)
    
    Services:
    - Online frame try-on tool
    - Home try-on program (5 frames for 5 days)
    - Eye exams with licensed specialists
    - Prescription fulfillment
    - 30-day returns
    - 1-year warranty on all frames
    
    IMPORTANT: When mentioning specific products, convert the [Product ID: X] format to a clickable link that says 
    "View Product" using HTML <a> tags. For example, convert [Product ID: 123] to <a href='/view-product/123/'>View Product</a>.
    
    Be friendly, concise, and informative. If you don't know something, suggest that the customer contact customer service.
    Always be supportive and avoid being judgmental about customer choices. Focus on helping them make informed decisions.
    """
    
    
    model = genai.GenerativeModel(
        model_name = "gemini-1.5-pro",
        generation_config=generation_config,
        system_instruction=system_instruction
    )
    
    # Prepare context with database info if available
    context_for_model = ""
    if personalized_context:
        context_for_model += f"Customer information:\n{personalized_context}\n\n"
    
    if db_context:
        context_for_model += f"Information from our database that might help answer the query:\n{db_context}\n\n"
    
    # Complete prompt with user question and guidance for the AI response
    prompt = f"{context_for_model}User query: {user_message}\n\n"
    prompt += "Please provide a helpful response based on the available information. "
    
    # Add specific guidance based on query type
    if query_type == "frame_info":
        prompt += "If recommending frames, include information about why they would work well for the customer. "
        prompt += "Highlight key features of recommended products."
    elif query_type == "specialist_info":
        prompt += "Include appointment booking information if relevant. "
    
    try:
        # Generate response from Gemini
        response = model.generate_content(prompt)
        
        # Track metrics for querying efficiency
        response_metadata = {
            'response': response.text,
            'db_data_used': bool(db_context),
            'query_type': query_type, 
            'personalized': bool(personalized_context)
        }
        
        return response_metadata
    except Exception as e:
        print(f"Gemini API error: {str(e)}")
        # Provide a fallback response if API fails
        fallback_responses = {
            "frame_info": "I can help you find the perfect frames for your face shape and style preferences. However, I'm having trouble accessing our product database right now. Please try again in a few moments or browse our collection online.",
            "review_info": "Our customers love sharing their experiences with our eyewear products. I'd be happy to show you our top-rated frames, but I'm having trouble accessing reviews at the moment.",
            "specialist_info": "We have qualified eye specialists available for consultations and eye exams. While I can't access their details right now, you can check our 'Book Appointment' page to find a specialist near you.",
            "general": "I'm sorry, I'm having trouble connecting to my knowledge base right now. Please try again later or contact our customer service for immediate assistance."
        }
        
        return {
            'response': fallback_responses.get(query_type, fallback_responses["general"]),
            'db_data_used': bool(db_context),
            'error': str(e)
        }

@csrf_exempt
def chatbot_test(request):
    """Simple test endpoint for the chatbot interface"""
    if request.method == "POST":
        user_message = request.POST.get('message', '')
        # Enhanced test response with mock data
        
        response_templates = [
            f"You asked: '{user_message}'\n\nI'm your SetFrames assistant. This is a test environment. In production, I'd provide helpful information about eyewear, face shapes, and frame recommendations.",
            f"Test bot received: '{user_message}'\n\nI can answer questions about our frame collections, help find products that match your style, and connect you with eye specialists.",
            f"Echo: '{user_message}'\n\nIn the live environment, I'd use our product database to provide personalized recommendations."
        ]
        import random
        return JsonResponse({'response': random.choice(response_templates)})
    return render(request, 'chatbot.html', {'initial_message': "This is the test chatbot. Try asking a question!"})

def seller_products(request, seller_id):
    """View to display all products from a specific seller"""
    # Get the seller or return 404 if not found
    seller = get_object_or_404(Seller, id=seller_id)
    
    # Filter products by this seller
    products = Lense.objects.filter(seller=seller).annotate(
        avg_rating=Avg('reviews__rating'),
        review_count=Count('reviews')
    )
    
    # Get categories for filter sidebar (optional)
    categories = Category.objects.all()
    
    context = {
        'P': products,  # Using 'P' to match your shop template
        'seller': seller,
        'categories': categories,
        'title': f"Products by {seller.first_name} {seller.last_name}"
    }
    
    return render(request, 'shop.html', context)  # Reuse your shop template or create a new one

from django.db.models.functions import Coalesce
def admin_product_list(request):
    # Get all products
    products = Lense.objects.all().order_by('-p_id')
    
    # Get all sellers for the filter dropdown
    sellers = Seller.objects.all()
    
    # Search functionality
    search_query = request.GET.get('search', '')
    if search_query:
        products = products.filter(
            Q(p_name__icontains=search_query) | 
            Q(p_desc__icontains=search_query) |
            Q(p_id__icontains=search_query)
        )
    
    # Filter by seller
    seller_id = request.GET.get('seller', '')
    if seller_id and seller_id != 'all':
        products = products.filter(seller_id=seller_id)
    
    # Filter by category
    category_id = request.GET.get('category', '')
    if category_id and category_id != 'all':
        products = products.filter(cat_id=category_id)
    
    # Add purchase analysis data
    products_with_analysis = []
    
    for product in products:
        # Get purchase orders for this product
        purchase_orders = PurchaseOrder.objects.filter(lens=product)
        
        # Calculate purchase metrics
        total_ordered = purchase_orders.aggregate(total=Coalesce(Sum('quantity'), 0))['total']
        order_count = purchase_orders.count()
        
        # Get status counts
        pending_count = purchase_orders.filter(status='PENDING').count()
        delivered_count = purchase_orders.filter(status='DELIVERED').count()
        cancelled_count = purchase_orders.filter(status='CANCELLED').count()
        
        # Get the last purchase date and status
        last_purchase = purchase_orders.order_by('-purchase_date').first()
        last_purchase_date = last_purchase.purchase_date if last_purchase else None
        last_purchase_status = last_purchase.status if last_purchase else None
        
        # Calculate average order size
        avg_order_size = 0
        if order_count > 0:
            avg_order_size = total_ordered / order_count
            
        # Add analysis data to product
        product.purchase_analysis = {
            'total_ordered': total_ordered,
            'order_count': order_count,
            'avg_order_size': round(avg_order_size, 2),
            'last_purchase_date': last_purchase_date,
            'last_purchase_status': last_purchase_status,
            'pending_count': pending_count,
            'delivered_count': delivered_count,
            'cancelled_count': cancelled_count,
            'recent_orders': purchase_orders.order_by('-purchase_date')[:3]  # Get 3 most recent orders
        }
        
        products_with_analysis.append(product)
    
    # Pagination
    paginator = Paginator(products_with_analysis, 10)  # Show 10 products per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'sellers': sellers,
        'categories': Category.objects.all(),
        'search_query': search_query,
        'selected_seller': seller_id,
        'selected_category': category_id,
    }
    
    return render(request, 'product_list.html', context)