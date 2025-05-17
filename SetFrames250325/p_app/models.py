from django.db import models
from django.contrib.auth.models import User


# Create your models here.

class Category(models.Model):
    name=models.CharField(max_length=100)
    def __str__(self):
        return self.name
    
class Seller(models.Model):
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    username = models.CharField(max_length=50, unique=True)
    password = models.CharField(max_length=50)
    email = models.EmailField(max_length=254, unique=True)
    mobile_phone = models.CharField(max_length=15)

    def __str__(self):
        return self.username


class Lense(models.Model):
    SHAPE_CHOICES = [
        ('aviator', 'Aviator'),
        ('square', 'Square'),
        ('oval', 'Oval'),
        ('rectangle', 'Rectangle'),
        ('round', 'Round'),
        ('geometric', 'Geometric'),
    ]
    
    p_id = models.AutoField(primary_key=True)
    p_name = models.CharField(max_length=50)
    p_desc = models.TextField()
    p_quantity = models.PositiveIntegerField()
    p_price = models.DecimalField(max_digits=10, decimal_places=2)
    p_image = models.ImageField(upload_to='uploads')
    shape = models.CharField(max_length=20, choices=SHAPE_CHOICES, default='round')
    seller=models.ForeignKey(Seller,on_delete=models.CASCADE,null=True)
    cat=models.ForeignKey(Category,on_delete=models.CASCADE,null=True)

    def __str__(self):
        return self.p_name
    
    class Meta:
        db_table = 'p_app'


class UserDetails(models.Model):
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    username = models.CharField(max_length=50, unique=True)
    password = models.CharField(max_length=50)
    email = models.EmailField(max_length=254, unique=True)
    mobile_phone = models.CharField(max_length=15)

    def __str__(self):
        return self.username
        


class admin_login(models.Model):
    username=models.CharField(max_length=100)
    password=models.CharField(max_length=100)


class cart(models.Model):
    customer = models.ForeignKey(UserDetails, on_delete=models.SET_NULL, null=True, blank=True)
    total = models.PositiveIntegerField(default=0)



class CartProduct(models.Model):
    cart = models.ForeignKey(cart, on_delete=models.CASCADE)
    product = models.ForeignKey(Lense, on_delete=models.CASCADE)
    rate = models.PositiveIntegerField()
    quantity = models.PositiveIntegerField()
    subtotal = models.PositiveIntegerField()

    def __str__(self):
        return "cart:" + str(self.cart.id) + "cartproduct:" + str(self.id)


ORDER_STATUS = (
    ("order recived", "order recived"),
    ("order processing", "order processing"),
    ("order on the way", "order on the way"),
    ("order completed", "order completed"),
    ("order cancelled", "order cancelled")
)


class Orders(models.Model):
    cart = models.ForeignKey(cart, on_delete=models.CASCADE)
    customer = models.ForeignKey(UserDetails, on_delete=models.SET_NULL, null=True, blank=True)
    total = models.PositiveIntegerField()
    order_status = models.CharField(max_length=50, choices=ORDER_STATUS)
    created_at = models.DateTimeField(auto_now_add=True)
    address = models.CharField(max_length=100,default="ssss")
    mobile  =models.CharField(max_length=50, default="45678")

    def __str__(self):
        return "order:" + str(self.id)

    @property
    def order_products(self):
        # This returns the products from the cart associated with this order.
        return self.cart.cartproduct_set.all()
    

class Wishlist(models.Model):
    user = models.ForeignKey(UserDetails, on_delete=models.CASCADE)
    products = models.ManyToManyField(Lense)

    def __str__(self):
        return f"Wishlist of {self.user.username}"
    
class PurchaseOrder(models.Model):
    lens = models.ForeignKey(Lense, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    seller = models.ForeignKey(Seller, on_delete=models.CASCADE)
    purchase_date = models.DateField(auto_now_add=True)
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('DELIVERED', 'Delivered'),
        ('CANCELLED', 'Cancelled'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def __str__(self):
        return f"Purchase Order for {self.quantity} {self.lens} from {self.seller} ({self.purchase_date})"
    


class UploadedImage(models.Model):
    image = models.ImageField(upload_to='uploads/')
    uploaded_at = models.DateTimeField(auto_now_add=True)


class EyeSpecialist(models.Model):
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=100)
    clinic_name = models.CharField(max_length=200)
    address = models.TextField()
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    phone = models.CharField(max_length=15)
    registration_date = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

class Appointment(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('CONFIRMED', 'Confirmed'),
        ('CANCELLED', 'Cancelled'),
        ('COMPLETED', 'Completed')
    ]

    patient = models.ForeignKey(UserDetails, on_delete=models.CASCADE)
    specialist = models.ForeignKey(EyeSpecialist, on_delete=models.CASCADE)
    appointment_date = models.DateField()
    appointment_time = models.TimeField()
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Appointment for {self.patient} with Dr. {self.specialist} on {self.appointment_date}"

class Review(models.Model):
    product = models.ForeignKey(Lense, on_delete=models.CASCADE, related_name='reviews')
    user = models.ForeignKey(UserDetails, on_delete=models.CASCADE)
    rating = models.IntegerField(choices=[(i, i) for i in range(1, 6)])  # 1 to 5 rating
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    order = models.ForeignKey(Orders, on_delete=models.CASCADE, null=True)

    class Meta:
        # Ensure one review per product per order
        unique_together = ('product', 'order', 'user')

    def __str__(self):
        return f"Review by {self.user.username} for {self.product.p_name}"
