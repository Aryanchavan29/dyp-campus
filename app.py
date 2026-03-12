from flask import Flask, render_template, redirect, url_for, flash, request, jsonify, session, Response
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_bcrypt import Bcrypt
from datetime import datetime, timedelta
import os
import uuid
import json
import re
import asyncio
import math
import random
import hashlib
import base64
from config import Config
from models import db, User, Course, Event, Club, Post, Enrollment, EventRegistration, ClubMember

# Import storage client
from storage_client import StorageClient, StorageError, HashValidationError

app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'

# Initialize storage client
STORAGE_GATEWAY_URL = os.environ.get('STORAGE_GATEWAY_URL', 'https://storage.example.com')
BACKEND_CANISTER_ID = os.environ.get('BACKEND_CANISTER_ID', 'canister-123')
PROJECT_ID = os.environ.get('PROJECT_ID', 'project-456')
BUCKET_NAME = os.environ.get('BUCKET_NAME', 'dyp-coet-uploads')

storage_client = StorageClient(
    bucket=BUCKET_NAME,
    storage_gateway_url=STORAGE_GATEWAY_URL,
    backend_canister_id=BACKEND_CANISTER_ID,
    project_id=PROJECT_ID
)

# Helper to run async functions in Flask
def run_async(coro):
    """Run an async coroutine in a synchronous context"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ============================================================
# MAIN ROUTES
# ============================================================

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        
        if user and bcrypt.check_password_hash(user.password_hash, password):
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('dashboard'))
        else:
            flash('Login unsuccessful. Please check email and password', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    # Route to appropriate dashboard based on user role
    if current_user.role == 'admin':
        return redirect(url_for('admin_dashboard'))
    elif current_user.role == 'teacher':
        return redirect(url_for('teacher_dashboard'))
    else:
        return redirect(url_for('student_dashboard'))

# ============================================================
# STUDENT DASHBOARD
# ============================================================

@app.route('/student/dashboard')
@login_required
def student_dashboard():
    """Render student dashboard"""
    if current_user.role != 'student' and current_user.role != 'admin':
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard'))
    return render_template('student_dashboard.html')

@app.route('/api/student/dashboard')
@login_required
def get_student_dashboard_data():
    """Get student dashboard data"""
    try:
        user = current_user
        
        # Get user's registered events
        registrations = EventRegistration.query.filter_by(user_id=user.id).all()
        registered_events = []
        for reg in registrations:
            event = Event.query.get(reg.event_id)
            if event and event.date >= datetime.now():
                registered_events.append({
                    'id': event.id,
                    'name': event.title,
                    'date': event.date.strftime('%d %b %Y'),
                    'dateMs': int(event.date.timestamp() * 1000),
                    'description': event.description,
                    'statusColor': get_status_color(event.category),
                    'bgColor': get_bg_color(event.category)
                })
        
        # Get user's clubs
        memberships = ClubMember.query.filter_by(user_id=user.id).all()
        user_clubs = []
        for membership in memberships:
            club = Club.query.get(membership.club_id)
            if club:
                user_clubs.append({
                    'name': club.name,
                    'description': club.description[:50] + '...' if len(club.description) > 50 else club.description,
                    'color': get_club_color(club.category)
                })
        
        # Get recent activity
        recent_activity = get_user_activity(user.id)
        
        # Get badges
        badges = get_user_badges(user.id)
        
        # Stats
        stats = [
            {
                'label': 'Events Registered',
                'value': str(len(registrations)),
                'icon': 'calendar-alt',
                'color': 'text-blue-600',
                'bg': 'bg-blue-50',
                'border': 'border-blue-200'
            },
            {
                'label': 'Clubs Joined',
                'value': str(len(user_clubs)),
                'icon': 'user',
                'color': 'text-indigo-600',
                'bg': 'bg-indigo-50',
                'border': 'border-indigo-200'
            },
            {
                'label': 'Badges Earned',
                'value': str(sum(1 for b in badges if b['earned'])),
                'icon': 'award',
                'color': 'text-amber-600',
                'bg': 'bg-amber-50',
                'border': 'border-amber-200'
            },
            {
                'label': 'GitHub Projects',
                'value': '1',
                'icon': 'code',
                'color': 'text-violet-600',
                'bg': 'bg-violet-50',
                'border': 'border-violet-200'
            }
        ]
        
        return jsonify({
            'success': True,
            'stats': stats,
            'events': registered_events[:5],
            'clubs': user_clubs[:3],
            'activity': recent_activity[:5],
            'badges': badges
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================
# TEACHER DASHBOARD
# ============================================================

@app.route('/teacher/dashboard')
@login_required
def teacher_dashboard():
    """Render teacher dashboard"""
    if current_user.role != 'teacher' and current_user.role != 'admin':
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard'))
    return render_template('teacher_dashboard.html')

@app.route('/api/teacher/dashboard')
@login_required
def get_teacher_dashboard_data():
    """Get teacher dashboard data"""
    try:
        # Get teacher's data
        teacher_id = current_user.id
        
        # Get doubts for this teacher
        doubts = get_teacher_doubts(teacher_id)
        
        # Get events managed by this teacher
        managed_events = get_teacher_events(teacher_id)
        
        # Stats
        stats = [
            {
                'label': 'Students Under Guidance',
                'value': '45',
                'icon': 'users',
                'color': 'text-amber-700',
                'bg': 'bg-amber-50',
                'border': 'border-amber-200'
            },
            {
                'label': 'Doubts Received',
                'value': str(len(doubts)),
                'icon': 'question-circle',
                'color': 'text-orange-700',
                'bg': 'bg-orange-50',
                'border': 'border-orange-200'
            },
            {
                'label': 'Events Managed',
                'value': str(len(managed_events)),
                'icon': 'calendar-alt',
                'color': 'text-yellow-700',
                'bg': 'bg-yellow-50',
                'border': 'border-yellow-200'
            },
            {
                'label': 'Announcements Posted',
                'value': '6',
                'icon': 'comment',
                'color': 'text-lime-700',
                'bg': 'bg-lime-50',
                'border': 'border-lime-200'
            }
        ]
        
        return jsonify({
            'success': True,
            'stats': stats,
            'doubts': doubts[:5],
            'events': managed_events[:3]
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================
# ADMIN DASHBOARD
# ============================================================

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    """Render admin dashboard"""
    if current_user.role != 'admin':
        flash('Access denied. Admin privileges required.', 'danger')
        return redirect(url_for('dashboard'))
    return render_template('admin_dashboard.html')

@app.route('/api/admin/stats')
@login_required
def get_admin_stats():
    """Get admin dashboard statistics"""
    if current_user.role != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    try:
        total_students = User.query.filter_by(role='student').count()
        active_events = Event.query.filter(Event.date >= datetime.now()).count()
        total_clubs = Club.query.count()
        posts_this_month = Post.query.filter(
            Post.created_at >= datetime.now().replace(day=1)
        ).count()
        
        stats = [
            {
                'label': 'Total Students',
                'value': f"{total_students:,}",
                'icon': 'users',
                'color': 'text-blue-600',
                'bg': 'bg-blue-50',
                'border': 'border-blue-200'
            },
            {
                'label': 'Active Events',
                'value': str(active_events),
                'icon': 'calendar-alt',
                'color': 'text-indigo-600',
                'bg': 'bg-indigo-50',
                'border': 'border-indigo-200'
            },
            {
                'label': 'Clubs',
                'value': str(total_clubs),
                'icon': 'user-check',
                'color': 'text-fuchsia-600',
                'bg': 'bg-fuchsia-50',
                'border': 'border-fuchsia-200'
            },
            {
                'label': 'Posts This Month',
                'value': str(posts_this_month),
                'icon': 'chart-line',
                'color': 'text-red-600',
                'bg': 'bg-red-50',
                'border': 'border-red-200'
            }
        ]
        
        return jsonify({'success': True, 'stats': stats})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/posts')
@login_required
def get_admin_posts():
    """Get recent posts for admin"""
    if current_user.role != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    try:
        posts = Post.query.order_by(Post.created_at.desc()).limit(10).all()
        posts_data = []
        for post in posts:
            user = User.query.get(post.user_id)
            posts_data.append({
                'id': post.id,
                'title': post.content[:50] + '...' if len(post.content) > 50 else post.content,
                'category': 'Announcement',
                'club': 'General',
                'date': post.created_at.strftime('%b %d, %Y'),
                'status': 'Published' if post.created_at > datetime.now() - timedelta(days=7) else 'Archived'
            })
        return jsonify({'success': True, 'posts': posts_data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/events')
@login_required
def get_admin_events():
    """Get events for admin"""
    if current_user.role != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    try:
        events = Event.query.order_by(Event.date).limit(10).all()
        events_data = []
        for event in events:
            registrations = EventRegistration.query.filter_by(event_id=event.id).count()
            status = 'Active' if event.date >= datetime.now() else 'Completed'
            if event.date > datetime.now() + timedelta(days=30):
                status = 'Upcoming'
            events_data.append({
                'name': event.title,
                'date': event.date.strftime('%d %b %Y'),
                'registrations': registrations,
                'status': status
            })
        return jsonify({'success': True, 'events': events_data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/users')
@login_required
def get_admin_users():
    """Get users for admin"""
    if current_user.role != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    try:
        users = User.query.limit(10).all()
        users_data = []
        for user in users:
            users_data.append({
                'name': user.full_name,
                'role': user.role or 'Student',
                'year': user.year or 'N/A',
                'branch': user.department or 'N/A',
                'status': 'Active' if user.is_active else 'Pending'
            })
        return jsonify({'success': True, 'users': users_data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================
# CLUB ROUTES
# ============================================================

@app.route('/clubs')
@login_required
def clubs():
    all_clubs = Club.query.all()
    memberships = ClubMember.query.filter_by(user_id=current_user.id).all()
    member_club_ids = [m.club_id for m in memberships]
    return render_template('clubs.html', clubs=all_clubs, member_ids=member_club_ids)

@app.route('/club/<int:club_id>')
@login_required
def club_detail(club_id):
    club = Club.query.get_or_404(club_id)
    members = ClubMember.query.filter_by(club_id=club_id).count()
    is_member = ClubMember.query.filter_by(user_id=current_user.id, club_id=club_id).first() is not None
    return render_template('club_detail.html', club=club, members=members, is_member=is_member)

@app.route('/api/club/join/<int:club_id>', methods=['POST'])
@login_required
def join_club(club_id):
    membership = ClubMember.query.filter_by(user_id=current_user.id, club_id=club_id).first()
    if membership:
        return jsonify({'success': False, 'message': 'Already a member'})
    
    membership = ClubMember(user_id=current_user.id, club_id=club_id)
    db.session.add(membership)
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Joined club successfully'})

@app.route('/api/club/register', methods=['POST'])
@login_required
def club_registration():
    """Handle club registration form submission"""
    try:
        data = request.get_json()
        
        required_fields = ['clubId', 'clubName', 'name', 'branch', 'year', 'reason']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({'success': False, 'error': f'Missing required field: {field}'}), 400
        
        if len(data['reason']) < 20:
            return jsonify({'success': False, 'error': 'Reason must be at least 20 characters long'}), 400
        
        return jsonify({
            'success': True,
            'message': 'Registration submitted successfully',
            'data': {
                'id': 123,
                'submitted_at': datetime.utcnow().isoformat()
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================
# EVENT ROUTES
# ============================================================

@app.route('/events')
@login_required
def events():
    all_events = Event.query.filter(Event.date >= datetime.now()).order_by(Event.date).all()
    registered = EventRegistration.query.filter_by(user_id=current_user.id).all()
    registered_ids = [r.event_id for r in registered]
    return render_template('events.html', events=all_events, registered_ids=registered_ids)

@app.route('/api/event/register/<int:event_id>', methods=['POST'])
@login_required
def register_event(event_id):
    event = Event.query.get_or_404(event_id)
    
    if event.registered >= event.capacity:
        return jsonify({'success': False, 'message': 'Event is full'})
    
    registration = EventRegistration.query.filter_by(user_id=current_user.id, event_id=event_id).first()
    if registration:
        return jsonify({'success': False, 'message': 'Already registered'})
    
    registration = EventRegistration(user_id=current_user.id, event_id=event_id)
    event.registered += 1
    db.session.add(registration)
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Registered successfully'})

# ============================================================
# CALENDAR ROUTES
# ============================================================

@app.route('/api/calendar/events')
@login_required
def get_calendar_events():
    """Get all events for calendar"""
    events = Event.query.all()
    clubs = Club.query.all()
    
    events_data = []
    for event in events:
        event_date_nano = int(event.date.timestamp() * 1_000_000_000)
        events_data.append({
            'id': str(event.id),
            'title': event.title,
            'description': event.description,
            'eventDate': event_date_nano,
            'location': event.location,
            'category': event.category,
            'clubId': str(event.club_id) if event.club_id else None
        })
    
    clubs_data = [{
        'id': str(club.id),
        'name': club.name,
        'full_name': club.full_name,
        'category': club.category
    } for club in clubs]
    
    return jsonify({
        'events': events_data,
        'clubs': clubs_data
    })

@app.route('/api/calendar/day-events')
@login_required
def get_day_events():
    """Get events for a specific day"""
    date_str = request.args.get('date')
    if not date_str:
        return jsonify({'error': 'Date required'}), 400
    
    try:
        selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Invalid date format'}), 400
    
    next_day = selected_date + timedelta(days=1)
    day_events = Event.query.filter(
        Event.date >= selected_date,
        Event.date < next_day
    ).all()
    
    events_data = []
    for event in day_events:
        club = Club.query.get(event.club_id) if event.club_id else None
        events_data.append({
            'id': str(event.id),
            'title': event.title,
            'description': event.description,
            'eventDate': int(event.date.timestamp() * 1_000_000_000),
            'location': event.location,
            'club': {
                'id': str(club.id) if club else None,
                'name': club.name if club else None
            } if club else None
        })
    
    return jsonify(events_data)

@app.route('/api/calendar/upcoming-24h')
@login_required
def get_upcoming_24h():
    """Get events in next 24 hours"""
    now = datetime.now()
    next_24h = now + timedelta(hours=24)
    
    upcoming = Event.query.filter(
        Event.date >= now,
        Event.date <= next_24h
    ).order_by(Event.date).all()
    
    events_data = []
    for event in upcoming:
        events_data.append({
            'id': str(event.id),
            'title': event.title,
            'eventDate': int(event.date.timestamp() * 1_000_000_000)
        })
    
    return jsonify(events_data)

@app.route('/api/calendar/month/<int:year>/<int:month>')
@login_required
def get_calendar_month(year, month):
    """Get calendar data for a specific month"""
    try:
        first_day = datetime(year, month, 1)
        if month == 12:
            last_day = datetime(year + 1, 1, 1) - timedelta(days=1)
        else:
            last_day = datetime(year, month + 1, 1) - timedelta(days=1)
        
        events = Event.query.filter(
            Event.date >= first_day,
            Event.date <= last_day
        ).all()
        
        events_by_date = {}
        for event in events:
            date_str = event.date.strftime('%Y-%m-%d')
            if date_str not in events_by_date:
                events_by_date[date_str] = []
            events_by_date[date_str].append({
                'id': event.id,
                'title': event.title,
                'time': event.date.strftime('%H:%M')
            })
        
        import calendar
        cal = calendar.monthcalendar(year, month)
        
        return jsonify({
            'success': True,
            'year': year,
            'month': month,
            'month_name': first_day.strftime('%B'),
            'calendar': cal,
            'events': events_by_date
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/calendar/events/<date>')
@login_required
def get_calendar_events_by_date(date):
    """Get events for a specific date"""
    try:
        date_obj = datetime.strptime(date, '%Y-%m-%d')
        next_day = date_obj + timedelta(days=1)
        
        events = Event.query.filter(
            Event.date >= date_obj,
            Event.date < next_day
        ).all()
        
        events_data = [{
            'id': event.id,
            'title': event.title,
            'description': event.description,
            'time': event.date.strftime('%I:%M %p'),
            'location': event.location,
            'category': event.category
        } for event in events]
        
        return jsonify({
            'success': True,
            'date': date,
            'events': events_data
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/calendar/range', methods=['POST'])
@login_required
def get_calendar_range():
    """Get events for a date range"""
    try:
        data = request.get_json()
        start_date = datetime.fromisoformat(data['start'].replace('Z', '+00:00'))
        end_date = datetime.fromisoformat(data['end'].replace('Z', '+00:00'))
        
        events = Event.query.filter(
            Event.date >= start_date,
            Event.date <= end_date
        ).all()
        
        events_data = [{
            'id': event.id,
            'title': event.title,
            'start': event.date.isoformat(),
            'end': (event.date + timedelta(hours=2)).isoformat(),
            'description': event.description,
            'location': event.location,
            'category': event.category
        } for event in events]
        
        return jsonify({
            'success': True,
            'events': events_data
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/calendar/download-ics', methods=['POST'])
@login_required
def download_event_ics():
    """Generate and download ICS file for event"""
    event_data = request.json
    if not event_data:
        return jsonify({'error': 'Event data required'}), 400
    
    event_date = datetime.fromtimestamp(event_data['eventDate'] / 1_000_000_000)
    end_date = event_date + timedelta(hours=2)
    
    def escape_ics(text):
        if not text:
            return ''
        return str(text).replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,').replace('\n', '\\n')
    
    ics_content = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//DYP COET//Event Calendar//EN
CALSCALE:GREGORIAN
METHOD:PUBLISH
BEGIN:VEVENT
UID:{event_data['id']}@dypcoet.edu
DTSTAMP:{datetime.now().strftime('%Y%m%dT%H%M%S')}Z
DTSTART:{event_date.strftime('%Y%m%dT%H%M%S')}Z
DTEND:{end_date.strftime('%Y%m%dT%H%M%S')}Z
SUMMARY:{escape_ics(event_data['title'])}
DESCRIPTION:{escape_ics(event_data.get('description', ''))}
LOCATION:{escape_ics(event_data.get('location', 'DYP COET'))}
STATUS:CONFIRMED
SEQUENCE:0
END:VEVENT
END:VCALENDAR"""
    
    return Response(
        ics_content,
        mimetype='text/calendar',
        headers={
            'Content-Disposition': f'attachment; filename=event_{event_data["id"]}.ics',
            'Content-Type': 'text/calendar; charset=utf-8'
        }
    )

# ============================================================
# COURSE ROUTES
# ============================================================

@app.route('/courses')
@login_required
def courses():
    all_courses = Course.query.all()
    enrolled = Enrollment.query.filter_by(user_id=current_user.id).all()
    enrolled_ids = [e.course_id for e in enrolled]
    return render_template('courses.html', courses=all_courses, enrolled_ids=enrolled_ids)

@app.route('/api/course/enroll/<int:course_id>', methods=['POST'])
@login_required
def enroll_course(course_id):
    course = Course.query.get_or_404(course_id)
    
    if course.enrolled >= course.capacity:
        return jsonify({'success': False, 'message': 'Course is full'})
    
    enrollment = Enrollment.query.filter_by(user_id=current_user.id, course_id=course_id).first()
    if enrollment:
        return jsonify({'success': False, 'message': 'Already enrolled'})
    
    enrollment = Enrollment(user_id=current_user.id, course_id=course_id)
    course.enrolled += 1
    db.session.add(enrollment)
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Enrolled successfully'})

# ============================================================
# POST ROUTES
# ============================================================

@app.route('/api/post/create', methods=['POST'])
@login_required
def create_post():
    content = request.form.get('content')
    if content:
        post = Post(user_id=current_user.id, content=content)
        db.session.add(post)
        db.session.commit()
        return jsonify({'success': True, 'post': {
            'id': post.id,
            'content': post.content,
            'author': current_user.full_name,
            'time': post.created_at.strftime('%Y-%m-%d %H:%M'),
            'likes': post.likes
        }})
    return jsonify({'success': False, 'message': 'Content cannot be empty'})

@app.route('/api/post/like/<int:post_id>', methods=['POST'])
@login_required
def like_post(post_id):
    post = Post.query.get_or_404(post_id)
    post.likes += 1
    db.session.commit()
    return jsonify({'success': True, 'likes': post.likes})

# ============================================================
# UPCOMING EVENTS ROUTES
# ============================================================

@app.route('/api/upcoming-events')
@login_required
def get_upcoming_events():
    """Get upcoming events for the strip"""
    now = datetime.now()
    upcoming_events = Event.query.filter(Event.date >= now).order_by(Event.date).limit(10).all()
    
    clubs = Club.query.all()
    
    events_data = []
    for event in upcoming_events:
        event_date_nano = int(event.date.timestamp() * 1_000_000_000)
        
        club = None
        if event.club_id:
            club = Club.query.get(event.club_id)
        
        events_data.append({
            'id': str(event.id),
            'title': event.title,
            'description': event.description,
            'eventDate': event_date_nano,
            'location': event.location,
            'category': event.category,
            'clubId': str(event.club_id) if event.club_id else None,
            'clubName': club.name if club else None,
            'club': {
                'id': str(club.id) if club else None,
                'name': club.name if club else None
            } if club else None
        })
    
    clubs_data = [{
        'id': str(club.id),
        'name': club.name,
        'full_name': club.full_name,
        'category': club.category
    } for club in clubs]
    
    return jsonify({
        'events': events_data,
        'clubs': clubs_data
    })

# ============================================================
# COMPLAINT BOX ROUTES
# ============================================================

@app.route('/api/complaint-box/submit', methods=['POST'])
@login_required
def submit_complaint_suggestion():
    """Handle complaint/suggestion form submission"""
    try:
        data = request.get_json()
        
        required_fields = ['name', 'rollNo', 'category', 'message', 'type']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({'success': False, 'error': f'Missing required field: {field}'}), 400
        
        if len(data['message'].strip()) < 20:
            return jsonify({'success': False, 'error': 'Message must be at least 20 characters long'}), 400
        
        if data['type'] not in ['complaint', 'suggestion']:
            return jsonify({'success': False, 'error': 'Invalid submission type'}), 400
        
        return jsonify({
            'success': True,
            'message': 'Submission received successfully',
            'data': {
                'id': str(uuid.uuid4()),
                'submitted_at': datetime.utcnow().isoformat(),
                'type': data['type']
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================
# FACULTY DOUBT ROUTES
# ============================================================

@app.route('/api/faculty/doubt', methods=['POST'])
@login_required
def submit_faculty_doubt():
    """Handle faculty doubt submission"""
    try:
        data = request.get_json()
        
        required_fields = ['name', 'branch', 'year', 'teacher', 'question']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({'success': False, 'error': f'Missing required field: {field}'}), 400
        
        if len(data['question'].strip()) < 10:
            return jsonify({'success': False, 'error': 'Question must be at least 10 characters long'}), 400
        
        return jsonify({
            'success': True,
            'message': 'Doubt submitted successfully',
            'data': {
                'id': str(uuid.uuid4()),
                'submitted_at': datetime.utcnow().isoformat(),
                'status': 'pending'
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/faculty/teachers')
@login_required
def get_teachers():
    """Get list of teachers for dropdown"""
    department = request.args.get('department', '')
    
    teachers = [
        {"id": 1, "name": "Dr. A. Patil", "department": "Computer Engineering"},
        {"id": 2, "name": "Prof. S. Kulkarni", "department": "Computer Engineering"},
        {"id": 3, "name": "Dr. R. Sharma", "department": "Electronics Engineering"},
        {"id": 4, "name": "Prof. M. Desai", "department": "Mechanical Engineering"},
        {"id": 5, "name": "Dr. P. Joshi", "department": "Civil Engineering"},
        {"id": 6, "name": "Prof. N. Sawant", "department": "Computer Engineering"},
        {"id": 7, "name": "Dr. K. Mehta", "department": "Electronics Engineering"},
        {"id": 8, "name": "Prof. V. Iyer", "department": "Information Technology"},
        {"id": 9, "name": "Dr. L. Rao", "department": "Computer Engineering"},
        {"id": 10, "name": "Prof. H. Singh", "department": "Mechanical Engineering"}
    ]
    
    if department:
        teachers = [t for t in teachers if t['department'].lower() == department.lower()]
    
    return jsonify({
        'success': True,
        'teachers': teachers
    })

@app.route('/api/faculty/doubt-history')
@login_required
def get_doubt_history():
    """Get student's doubt submission history"""
    history = [
        {
            'id': '1',
            'teacher': 'Dr. A. Patil',
            'question': 'Can you explain the concept of polymorphism in OOP?',
            'status': 'answered',
            'submitted_at': '2024-03-10T10:30:00',
            'answered_at': '2024-03-11T14:20:00',
            'answer': 'Polymorphism allows objects to take multiple forms...'
        },
        {
            'id': '2',
            'teacher': 'Prof. S. Kulkarni',
            'question': 'What is the difference between process and thread?',
            'status': 'pending',
            'submitted_at': '2024-03-12T09:15:00'
        }
    ]
    
    return jsonify({
        'success': True,
        'history': history
    })

# ============================================================
# GITHUB PROJECTS ROUTES
# ============================================================

@app.route('/api/github/projects')
@login_required
def get_github_projects():
    """Fetch GitHub projects from students"""
    try:
        sample_projects = [
            {
                'id': 1,
                'name': 'DYP Social Network',
                'description': 'A college social network platform built with Flask and React',
                'language': 'Python',
                'stars': 45,
                'forks': 12,
                'html_url': 'https://github.com/dypcoet/social-network',
                'updated_at': '2024-03-15'
            },
            {
                'id': 2,
                'name': 'Campus Connect',
                'description': 'Mobile app for student collaboration and event management',
                'language': 'JavaScript',
                'stars': 32,
                'forks': 8,
                'html_url': 'https://github.com/dypcoet/campus-connect',
                'updated_at': '2024-03-10'
            },
            {
                'id': 3,
                'name': 'E-Learning Platform',
                'description': 'Online learning management system for D
