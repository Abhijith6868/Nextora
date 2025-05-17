from dataclasses import fields

from django import forms
from . models import Orders, Seller, UploadedImage


class  checkoutform(forms.ModelForm):
    class Meta:
        model=Orders
        fields=["address","mobile"]

from .models import Category

class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name']

class OrderForm(forms.Form):
    quantity = forms.IntegerField(label='Quantity', min_value=1)

from django import forms



class ImageUploadForm(forms.Form):
    image = forms.ImageField(
        required=True,
        error_messages={
            'required': 'Please select an image file',
            'invalid': 'File type not supported'
        },
        widget=forms.FileInput(attrs={
            'accept': 'image/jpeg,image/png',
            'class': 'form-control'
        })
    )

    def clean_image(self):
        image = self.cleaned_data.get('image')
        if image:
            if image.size > 5 * 1024 * 1024:  # 5MB limit
                raise forms.ValidationError("Image file too large ( > 5MB )")
            if image.content_type not in ['image/jpeg', 'image/png']:
                raise forms.ValidationError("Please upload a JPEG or PNG image")
        return image
    

#query tool
from django import forms

class QueryForm(forms.Form):
    MODEL_CHOICES = [
        ('Category', 'Category'),
        ('Seller', 'Seller'),
        ('Lense', 'Lense'),
        ('UserDetails', 'User Details'),
        ('cart', 'Cart'),
        ('CartProduct', 'Cart Product'),
        ('Orders', 'Orders'),
        ('Wishlist', 'Wishlist'),
        ('PurchaseOrder', 'Purchase Order'),
        ('EyeSpecialist', 'Eye Specialist'),
        ('Appointment', 'Appointment'),
        ('Review', 'Review'),
    ]
    
    model = forms.ChoiceField(choices=MODEL_CHOICES, required=True, 
                             widget=forms.Select(attrs={'class': 'form-control'}))
    
    filters = forms.CharField(required=False, 
                             widget=forms.TextInput(attrs={'class': 'form-control', 
                                                          'placeholder': 'Field=value, Field__lt=value'}))
    
    fields = forms.CharField(required=False, 
                            widget=forms.TextInput(attrs={'class': 'form-control', 
                                                         'placeholder': 'field1,field2,field3'}))
    
    order_by = forms.CharField(required=False, 
                              widget=forms.TextInput(attrs={'class': 'form-control', 
                                                           'placeholder': 'field or -field for descending'}))
    
    limit = forms.IntegerField(required=False, min_value=1, 
                              widget=forms.NumberInput(attrs={'class': 'form-control', 
                                                             'placeholder': 'Number of results'}))
