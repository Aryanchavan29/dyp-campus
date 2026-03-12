from app import app, db
from models import User, Course, Event, Club
from flask_bcrypt import Bcrypt
from datetime import datetime, timedelta

bcrypt = Bcrypt(app)

def init_database():
    with app.app_context():
        # Drop all tables and recreate
        db.drop_all()
        db.create_all()
        
        # Create demo user
        demo_user = User(
            email='student@gmail.com',
            full_name='Demo Student',
            student_id='DYP2025001',
            department='Computer Engineering',
            year=3,
            bio='Passionate about technology and innovation'
        )
        demo_user.password_hash = bcrypt.generate_password_hash('student123').decode('utf-8')
        db.session.add(demo_user)
        
        # Create sample courses
        courses = [
            Course(code='CS101', name='Introduction to Programming', 
                   description='Learn fundamentals of programming using Python', 
                   department='Computer Engineering', credits=4, 
                   instructor='Dr. Smith', schedule='Mon/Wed 10:00-11:30', capacity=60),
            Course(code='CS201', name='Data Structures and Algorithms', 
                   description='Advanced data structures and algorithm analysis', 
                   department='Computer Engineering', credits=4, 
                   instructor='Dr. Johnson', schedule='Tue/Thu 13:00-14:30', capacity=50),
            Course(code='EE101', name='Basic Electrical Engineering', 
                   description='Fundamentals of electrical circuits', 
                   department='Electrical Engineering', credits=3, 
                   instructor='Prof. Williams', schedule='Mon/Wed 14:00-15:30', capacity=45),
            Course(code='ME101', name='Engineering Mechanics', 
                   description='Principles of mechanics and dynamics', 
                   department='Mechanical Engineering', credits=3, 
                   instructor='Dr. Brown', schedule='Tue/Thu 09:00-10:30', capacity=40),
        ]
        for course in courses:
            db.session.add(course)
        
        # Create sample events
        events = [
            Event(title='TECHNOTSAV 2K25 - Cosmos of Innovation',
                  description='National Level Technical Fest celebrating innovation and technology',
                  date=datetime(2026, 3, 20, 9, 0),
                  location='Main Auditorium',
                  category='technical',
                  capacity=500,
                  image_url='/static/images/techfest.jpg'),
            Event(title='ARPAN SPORTS MEET',
                  description='Grand annual sports event celebrating athletic spirit',
                  date=datetime(2026, 3, 15, 8, 0),
                  location='Sports Complex',
                  category='sports',
                  capacity=300,
                  image_url='/static/images/sports.jpg'),
            Event(title='Coding Competition',
                  description='Inter-college coding competition',
                  date=datetime(2026, 3, 25, 10, 0),
                  location='CS Department',
                  category='technical',
                  capacity=100,
                  image_url='/static/images/coding.jpg'),
            Event(title='Robotics Workshop',
                  description='Hands-on workshop on robotics',
                  date=datetime(2026, 3, 26, 14, 0),
                  location='Robotics Lab',
                  category='workshop',
                  capacity=50,
                  image_url='/static/images/robotics.jpg'),
        ]
        for event in events:
            db.session.add(event)
        
        # Create sample clubs
        clubs = [
            Club(name='Coding Club',
                 description='For programming enthusiasts',
                 category='technical',
                 meeting_schedule='Every Friday 16:00-18:00',
                 contact_email='codingclub@dypcoet.edu',
                 logo_url='/static/images/coding_club.png'),
            Club(name='Robotics Club',
                 description='Build and program robots',
                 category='technical',
                 meeting_schedule='Every Wednesday 15:00-17:00',
                 contact_email='robotics@dypcoet.edu',
                 logo_url='/static/images/robotics_club.png'),
            Club(name='Sports Club',
                 description='For sports and fitness enthusiasts',
                 category='sports',
                 meeting_schedule='Daily 06:00-07:30',
                 contact_email='sports@dypcoet.edu',
                 logo_url='/static/images/sports_club.png'),
            Club(name='Cultural Committee',
                 description='Organize cultural events',
                 category='cultural',
                 meeting_schedule='Every Tuesday 17:00-18:30',
                 contact_email='cultural@dypcoet.edu',
                 logo_url='/static/images/cultural.png'),
        ]
        for club in clubs:
            db.session.add(club)
        
        db.session.commit()
        print("Database initialized with demo data!")

if __name__ == '__main__':
    init_database()
