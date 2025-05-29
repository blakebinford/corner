# core/dashboard.py
import json
from datetime import timedelta, datetime
from django.utils import timezone
from accounts.models import User
from competitions.models import Competition, AthleteCompetition

def dashboard_callback(request, context):
    # — date range —
    try:
        start = datetime.strptime(request.GET.get('start_date', ''), '%Y-%m-%d').date()
    except:
        start = timezone.now().date() - timedelta(days=30)
    try:
        end = datetime.strptime(request.GET.get('end_date', ''), '%Y-%m-%d').date()
    except:
        end = timezone.now().date()

    days = []
    current = start
    while current <= end:
        days.append(current)
        current += timedelta(days=1)
    labels = [d.strftime('%Y-%m-%d') for d in days]

    # — metrics —
    total_users = User.objects.count()
    total_comps = Competition.objects.count()
    total_regs = AthleteCompetition.objects.filter(payment_status='paid').count()
    pending_regs = AthleteCompetition.objects.filter(payment_status='pending').count()

    awaiting_comps = Competition.objects.filter(approval_status='waiting').order_by('comp_date')

    # — signups per role —
    roles = [r[0] for r in User._meta.get_field('role').choices]
    signups = {role: [] for role in roles}
    for day in days:
        start_dt = datetime.combine(day, datetime.min.time())
        end_dt   = datetime.combine(day, datetime.max.time())
        for role in roles:
            signups[role].append(
                User.objects.filter(date_joined__range=(start_dt, end_dt), role=role).count()
            )

    # — registrations over time —
    reg_counts = []
    for day in days:
        start_dt = datetime.combine(day, datetime.min.time())
        end_dt   = datetime.combine(day, datetime.max.time())
        reg_counts.append(
            AthleteCompetition.objects.filter(registration_date__range=(start_dt, end_dt)).count()
        )

    # — competitions over time —
    comp_counts = [ Competition.objects.filter(comp_date=day).count() for day in days ]

    # — recent activity —
    recent_users = User.objects.order_by('-date_joined')[:5]
    recent_regs  = AthleteCompetition.objects.order_by('-registration_date')[:5]
    recent_comps = Competition.objects.order_by('-comp_date')[:5]

    context.update({
        'start_date':        start,
        'end_date':          end,
        'total_users':       total_users,
        'total_comps':       total_comps,
        'total_regs':        total_regs,
        'pending_regs':      pending_regs,
        'awaiting_comps':    awaiting_comps,
        'trend_days':        labels,
        'trend_roles':       roles,
        'trend_signups':     signups,
        'trend_reg_days':    labels,
        'trend_reg_counts':  reg_counts,
        'trend_comp_days':   labels,
        'trend_comp_counts': comp_counts,
        'recent_users':      recent_users,
        'recent_regs':       recent_regs,
        'recent_comps':      recent_comps,
    })
    return context
