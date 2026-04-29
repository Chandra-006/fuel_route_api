"""
views.py
--------
This file defines the API endpoint for the Fuel Route Planner.
It receives the POST request, validates the input,
calls the core logic in fuel_optimizer.py, and returns the result.
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .fuel_optimizer import plan_route


class RoutePlannerView(APIView):
    """
    API View for planning a fuel-optimized route.

    Endpoint : POST /api/route/plan/
    Request  : { "start": "New York, NY", "finish": "Los Angeles, CA" }
    Response : Route details with optimal fuel stops and total cost
    """

    def post(self, request):
        # ---------------------------------------------------------------------
        # Extract 'start' and 'finish' from the request body
        # request.data is a dictionary parsed from the JSON request body
        # ---------------------------------------------------------------------
        start  = request.data.get('start')
        finish = request.data.get('finish')

        # ---------------------------------------------------------------------
        # Validate that both fields are provided
        # Return a 400 Bad Request if either is missing
        # ---------------------------------------------------------------------
        if not start or not finish:
            return Response(
                {"error": "Both 'start' and 'finish' fields are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # -----------------------------------------------------------------
            # Call the main route planning function from fuel_optimizer.py
            # This does all the heavy lifting:
            #   - Geocodes start/finish
            #   - Fetches the route
            #   - Finds optimal fuel stops
            #   - Calculates total cost
            # -----------------------------------------------------------------
            result = plan_route(start, finish)

            # Return the result with a 200 OK status
            return Response(result, status=status.HTTP_200_OK)

        except ValueError as e:
            # ValueError is raised when a location can't be geocoded
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

        except Exception as e:
            # Catch-all for any unexpected errors (network issues, etc.)
            return Response(
                {"error": f"Something went wrong: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )