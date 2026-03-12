from flask import Flask, render_template, redirect, url_for, flash, request, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_bcrypt import Bcrypt
from datetime import datetime, timedelta
import os
from config import Config
from models import db, User, Course, Event, Club, Post, Enrollment, EventRegistration, ClubMember

app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

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
    # Get upcoming events
    upcoming_events = Event.query.filter(Event.date >= datetime.now()).order_by(Event.date).limit(5).all()
    
    # Get user's courses
    enrolled_courses = Enrollment.query.filter_by(user_id=current_user.id).all()
    courses = [Course.query.get(enc.course_id) for enc in enrolled_courses]
    
    # Get recent posts
    recent_posts = Post.query.order_by(Post.created_at.desc()).limit(10).all()
    
    # Get clubs
    clubs = Club.query.limit(5).all()
    
    return render_template('dashboard.html', 
                         events=upcoming_events,
                         courses=courses,
                         posts=recent_posts,
                         clubs=clubs)

@app.route('/courses')
@login_required
def courses():
    all_courses = Course.query.all()
    enrolled = Enrollment.query.filter_by(user_id=current_user.id).all()
    enrolled_ids = [e.course_id for e in enrolled]
    return render_template('courses.html', courses=all_courses, enrolled_ids=enrolled_ids)

@app.route('/enroll/<int:course_id>', methods=['POST'])
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

@app.route('/events')
@login_required
def events():
    all_events = Event.query.filter(Event.date >= datetime.now()).order_by(Event.date).all()
    registered = EventRegistration.query.filter_by(user_id=current_user.id).all()
    registered_ids = [r.event_id for r in registered]
    return render_template('events.html', events=all_events, registered_ids=registered_ids)

@app.route('/register_event/<int:event_id>', methods=['POST'])
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

@app.route('/clubs')
@login_required
def clubs():
    all_clubs = Club.query.all()
    memberships = ClubMember.query.filter_by(user_id=current_user.id).all()
    member_club_ids = [m.club_id for m in memberships]
    return render_template('clubs.html', clubs=all_clubs, member_ids=member_club_ids)

@app.route('/join_club/<int:club_id>', methods=['POST'])
@login_required
def join_club(club_id):
    membership = ClubMember.query.filter_by(user_id=current_user.id, club_id=club_id).first()
    if membership:
        return jsonify({'success': False, 'message': 'Already a member'})
    
    membership = ClubMember(user_id=current_user.id, club_id=club_id)
    db.session.add(membership)
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Joined club successfully'})

@app.route('/create_post', methods=['POST'])
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

@app.route('/like_post/<int:post_id>', methods=['POST'])
@login_required
def like_post(post_id):
    post = Post.query.get_or_404(post_id)
    post.likes += 1
    db.session.commit()
    return jsonify({'success': True, 'likes': post.likes})

@app.route('/calendar_events')
@login_required
def calendar_events():
    month = request.args.get('month', datetime.now().month, type=int)
    year = request.args.get('year', datetime.now().year, type=int)
    
    start_date = datetime(year, month, 1)
    if month == 12:
        end_date = datetime(year + 1, 1, 1)
    else:
        end_date = datetime(year, month + 1, 1)
    
    events = Event.query.filter(Event.date >= start_date, Event.date < end_date).all()
    
    events_data = [{
        'id': e.id,
        'title': e.title,
        'date': e.date.strftime('%Y-%m-%d'),
        'category': e.category
    } for e in events]
    
    return jsonify(events_data)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
