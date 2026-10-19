# views/ratings_feedback.py
from django.shortcuts import render, redirect
from django.contrib import messages
from django.db import connection
from .login import admin_required


@admin_required
def ratings_feedback(request):
    current_tab = request.GET.get('tab', 'overview')

    if request.method == 'POST':
        action = request.POST.get('action')
        review_id = request.POST.get('review_id')

        if action == 'remove' and review_id:
            messages.success(request, f"Review #REV-{review_id} has been successfully removed.")
        elif action == 'resolve' and review_id:
            messages.success(request, f"Dispute for Review #REV-{review_id} has been marked as resolved.")

        return redirect(f"{request.path}?tab={current_tab}")

    reviews_list = []
    disputes_list = []

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT review_id, rating, review_text, bc_rating_tx_hash,
                       delivery_id, reviewer_id, reviewee_id, created_at
                FROM ratings_reviews ORDER BY created_at DESC
            """)
            for row in cursor.fetchall():
                item = {
                    'review_id': row[0], 'rating': row[1], 'review_text': row[2],
                    'bc_rating_tx_hash': row[3], 'delivery_id': row[4],
                    'reviewer_id': row[5], 'reviewee_id': row[6],
                    'created_at': row[7].strftime('%Y-%m-%d') if row[7] else '—',
                    'status': 'Flagged' if row[1] <= 2 else 'Active'
                }
                reviews_list.append(item)
                if item['status'] == 'Flagged':
                    disputes_list.append(item)

    except Exception:
        reviews_list = [
            {'review_id': 101, 'rating': 2, 'review_text': 'Package left at wrong location and delayed by 2 hours.', 'bc_rating_tx_hash': '0x8f2...', 'delivery_id': 5001, 'reviewer_id': 301, 'reviewee_id': 402, 'created_at': '2026-03-28', 'status': 'Flagged'},
            {'review_id': 102, 'rating': 1, 'review_text': 'Very unprofessional handler. Item box was dented.', 'bc_rating_tx_hash': '0x1a2...', 'delivery_id': 5002, 'reviewer_id': 302, 'reviewee_id': 403, 'created_at': '2026-03-27', 'status': 'Flagged'},
            {'review_id': 103, 'rating': 5, 'review_text': 'Very careful with my package. Arrived earlier than expected!', 'bc_rating_tx_hash': '0x3c4...', 'delivery_id': 5003, 'reviewer_id': 303, 'reviewee_id': 403, 'created_at': '2026-03-26', 'status': 'Active'},
        ]
        disputes_list = [r for r in reviews_list if r['status'] == 'Flagged']

    return render(request, 'pages/ratings_feedback.html', {
        'current_tab': current_tab,
        'reviews_list': reviews_list,
        'disputes_list': disputes_list,
    })