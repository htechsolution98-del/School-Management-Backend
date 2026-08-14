from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet
from rest_framework import generics
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import authenticate
from django.utils import timezone
from .models import *
from .serializer import *
from .permissions import *
from .utils import *
import datetime
from django.core.cache import cache
from django.db import transaction
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import api_view, permission_classes

class StockItemsViewset(ModelViewSet):
    def get_permissions(self):
        if self.request.method=='GET':
            return [IsAuthenticated()]
        else:
            return [IsAuthenticated(),Isinventory()]

    queryset=StockItems.objects.all()
    serializer_class= StockItemsSerializer

    def get_queryset(self):
        return StockItems.objects.filter(school=self.request.user.school)
        

    def perform_create(self, serializer):
        serializer.save(school=self.request.user.school)   

    def perform_update(self, serializer):
        return super().perform_update(serializer)
    
    def perform_destroy(self, instance):
        return super().perform_destroy(instance)
    




class StockRequestViewset(ModelViewSet):
    permission_classes = [IsAuthenticated, Isteacher]
        
    queryset=StockRequest.objects.all()
    serializer_class=StockRequestSerializer

    def get_queryset(self):
        if self.request.user.groups.filter(name="INVENTORY").exists():
            return StockRequest.objects.filter(school=self.request.user.school)

        return StockRequest.objects.filter(teacher=self.request.user.staff)
    def perform_create(self, serializer):
        serializer.save(school=self.request.user.school,teacher=self.request.user.staff)
    def update(self, request, *args, **kwargs):
        stock_request = self.get_object()

        if stock_request.status != "pending":
            return Response(
                {"error": "Only pending requests can be updated."},
                status=status.HTTP_400_BAD_REQUEST
            )

        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        stock_request = self.get_object()

        if stock_request.status != "pending":
            return Response(
                {"error": "Only pending requests can be updated."},
                status=status.HTTP_400_BAD_REQUEST
            )

        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        stock_request = self.get_object()

        if stock_request.status != "pending":
            return Response(
                {"error": "Only pending requests can be deleted."},
                status=status.HTTP_400_BAD_REQUEST
            )

        stock_request.delete()

        return Response(
            {"message": "Request deleted successfully."},
            status=status.HTTP_204_NO_CONTENT
        )
    


class InventoryStockRequestViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated, Isinventory]
    serializer_class = StockRequestSerializer
    queryset = StockRequest.objects.all()

   

    def get_queryset(self):
        return StockRequest.objects.filter(
            school=self.request.user.school
        )

    def partial_update(self, request, *args, **kwargs):
        stock_request = self.get_object()

        if stock_request.status != "pending":
            return Response(
                {"error": "Request has already been processed."},
                status=status.HTTP_400_BAD_REQUEST
            )

        status_value = request.data.get("status")

        if status_value not in ["approved", "rejected"]:
            return Response(
                {"error": "Status must be 'approved' or 'rejected'."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if status_value == "approved":
            item = stock_request.stock_item

            if item.quantity < stock_request.quantity:
                return Response(
                    {"error": "Insufficient stock available."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            item.quantity -= stock_request.quantity
            item.save()

        stock_request.status = status_value
        stock_request.save()

        serializer = self.get_serializer(stock_request)
        return Response(serializer.data) 

    


class AssetViewSet(ModelViewSet):
    permission_classes=[Isinventory]
    queryset=Asset.objects.all()
    serializer_class=AssetSerializer

    def get_queryset(self):
       return Asset.objects.filter(school=self.request.user.school)
   
    def perform_create(self, serializer):
       serializer.save(school=self.request.user.school)

    def perform_update(self, serializer):
        return super().perform_update(serializer)

   



class AssetMaintenanceViewSet(ModelViewSet):
    permission_classes=[Isinventory]
    queryset=AssetMaintenance.objects.all()
    serializer_class=AssetMaintenanceSerializer

    def get_queryset(self):
       return AssetMaintenance.objects.filter(school=self.request.user.school)
   
    def perform_create(self, serializer):
       serializer.save(school=self.request.user.school)

    def partial_update(self, request, *args, **kwargs):
        return super().partial_update(request, *args, **kwargs)
    


class ProcurementViewSet(ModelViewSet):
    permission_classes=[Isinventory]
    queryset=Procurement.objects.all()
    serializer_class=ProcurementSerializer

    def get_queryset(self):
       return Procurement.objects.filter(school=self.request.user.school)
   
    def perform_create(self, serializer):
       serializer.save(school=self.request.user.school)

    def perform_update(self, serializer):
        procurement = serializer.save()

        if procurement.status == "received":
            procurement.restock()
        
    


class ProcurementItemViewSet(ModelViewSet):
    permission_classes=[Isinventory]
    queryset=ProcurementItem.objects.all()
    serializer_class=ProcurementItemSerializer

    def get_queryset(self):
       return ProcurementItem.objects.filter(procurement__school=self.request.user.school)
   
    def perform_create(self, serializer):
       serializer.save()

    def partial_update(self, request, *args, **kwargs):
        return super().partial_update(request, *args, **kwargs)




class LossPreventionViewset(ModelViewSet):
    queryset=LossPrevention.objects.all()
    serializer_class=LosspreventionSerializer
    permission_classes=[Isinventory]

    def get_queryset(self):
        return LossPrevention.objects.filter(school=self.request.user.school)
    
    def perform_create(self, serializer):
        serializer.save(school=self.request.user.school)
    



