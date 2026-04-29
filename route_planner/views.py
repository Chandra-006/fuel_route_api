from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .fuel_optimizer import plan_route


class RoutePlannerView(APIView):
    def post(self, request):
        start = request.data.get('start')
        finish = request.data.get('finish')

        if not start or not finish:
            return Response(
                {"error": "Both 'start' and 'finish' fields are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            result = plan_route(start, finish)
            return Response(result, status=status.HTTP_200_OK)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": f"Something went wrong: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)