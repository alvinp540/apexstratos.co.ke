from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.db.models import Count, Avg, Q

from .models import VendorJob, VendorRating
from .serializers import VendorJobSerializer, VendorRatingSerializer
from apps.accounts.permissions import IsApprovedVendor, IsProfessional


class VendorJobListCreateView(APIView):
    permission_classes = (IsApprovedVendor,)

    def get(self, request):
        jobs = VendorJob.objects.filter(vendor=request.user).order_by('-created_at')
        return Response(VendorJobSerializer(jobs, many=True).data)

    def post(self, request):
        serializer = VendorJobSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(vendor=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class VendorJobDetailView(APIView):
    permission_classes = (IsApprovedVendor,)

    def get(self, request, job_id):
        job = get_object_or_404(VendorJob, id=job_id, vendor=request.user)
        return Response(VendorJobSerializer(job).data)

    def put(self, request, job_id):
        job = get_object_or_404(VendorJob, id=job_id, vendor=request.user)
        serializer = VendorJobSerializer(job, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def patch(self, request, job_id):
        job = get_object_or_404(VendorJob, id=job_id, vendor=request.user)
        serializer = VendorJobSerializer(job, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, job_id):
        job = get_object_or_404(VendorJob, id=job_id, vendor=request.user, status='draft')
        job.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PublishJobView(APIView):
    permission_classes = (IsApprovedVendor,)

    def post(self, request, job_id):
        job = get_object_or_404(VendorJob, id=job_id, vendor=request.user, status='draft')
        job.status = 'open'
        job.save(update_fields=['status'])
        from apps.router.engine import route_job
        route_job(str(job.id))
        return Response({'message': 'Job published and routing initiated.'})


class RateProfessionalView(APIView):
    permission_classes = (IsApprovedVendor,)

    def post(self, request, job_id):
        job = get_object_or_404(
            VendorJob, id=job_id, vendor=request.user, status='completed'
        )
        if hasattr(job, 'rating'):
            return Response({'error': 'Job already rated.'}, status=status.HTTP_400_BAD_REQUEST)
        serializer = VendorRatingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(
            vendor=request.user,
            professional=job.assigned_professional,
            job=job,
        )
        from apps.trust_engine.engine import recalculate_trust_score
        recalculate_trust_score(job.assigned_professional, reason='Vendor rating received')
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class JobMatchesView(APIView):
    permission_classes = (IsApprovedVendor,)

    def get(self, request, job_id):
        from apps.fraud.models import Opportunity
        job = get_object_or_404(VendorJob, id=job_id, vendor=request.user)
        opps = Opportunity.objects.filter(job=job).select_related(
            'professional__profile', 'professional__trust_score'
        ).order_by('-router_score')
        data = [
            {
                'professional_id': str(o.professional_id),
                'full_name': getattr(getattr(o.professional, 'profile', None), 'full_name', ''),
                'profession': getattr(getattr(o.professional, 'profile', None), 'profession', ''),
                'status': o.status,
            }
            for o in opps
        ]
        return Response(data)


class VendorDashboardView(APIView):
    permission_classes = (IsApprovedVendor,)

    def get(self, request):
        jobs = VendorJob.objects.filter(vendor=request.user)
        return Response({
            'total_jobs': jobs.count(),
            'open_jobs': jobs.filter(status='open').count(),
            'completed_jobs': jobs.filter(status='completed').count(),
            'avg_rating_given': VendorRating.objects.filter(
                vendor=request.user
            ).aggregate(avg=Avg('overall_score'))['avg'],
        })


class ProfessionalOpportunityView(APIView):
    permission_classes = (IsProfessional,)

    def get(self, request):
        jobs = VendorJob.objects.filter(status='open').order_by('-priority', '-created_at')
        profession = request.query_params.get('profession')
        skill = request.query_params.get('skill')
        minimum_score = float(request.query_params.get('min_merit', 0) or 0)
        if profession:
            jobs = jobs.filter(profession_required__icontains=profession)
        if skill:
            jobs = jobs.filter(skills_required__icontains=skill)
        jobs = jobs.filter(min_trust_score__gte=minimum_score)
        return Response(VendorJobSerializer(jobs[:50], many=True).data)
