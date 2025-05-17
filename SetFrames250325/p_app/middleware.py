from django.shortcuts import redirect
from django.urls import reverse
import re

class RestrictNonCustomersMiddleware:
    """Middleware to prevent admin, Seller, and EyeSpecialist from accessing restricted pages"""
    
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
            restricted_paths = [
                reverse('my-cart'), 
                reverse('my-orders'), 
                reverse('wishlist'),
                reverse('book_appointment'),
                reverse('my_appointments'),
            ]

            # Check if user is not a customer
            if request.session.get('user_type') != 'user':
                # Check exact path matches
                if request.path in restricted_paths:
                    return redirect('not_allowed')
                    
                # Check profile pages
                profile_pattern = r'^/profile/[^/]+/$'
                if re.match(profile_pattern, request.path):
                    return redirect('not_allowed')
                    
                # Check if path contains 'wishlist' anywhere in the URL
                # This catches any wishlist-related functionality
                if 'wishlist' in request.path.lower():
                    return redirect('not_allowed')
                # Alternatively, you can check specifically for add_to_wishlist pattern
                add_wishlist_pattern = r'^/add_to_wishlist/\d+/$'
                if re.match(add_wishlist_pattern, request.path):
                    return redirect('not_allowed')

            return self.get_response(request)
