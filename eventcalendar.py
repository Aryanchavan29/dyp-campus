from datetime import datetime, timedelta
import time
import json

# Add these routes to your existing app.py

@app.route('/api/calendar/events')
@login_required
def get_calendar_events():
    """Get all events for calendar"""
    events = Event.query.all()
    clubs = Club.query.all()
    
    events_data = []
    for event in events:
        # Convert datetime to nanoseconds timestamp for JS compatibility
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
    
    # Get events for this day
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

@app.route('/api/calendar/download-ics', methods=['POST'])
@login_required
def download_event_ics():
    """Generate and download ICS file for event"""
    event_data = request.json
    if not event_data:
        return jsonify({'error': 'Event data required'}), 400
    
    # Create ICS content
    event_date = datetime.fromtimestamp(event_data['eventDate'] / 1_000_000_000)
    end_date = event_date + timedelta(hours=1)  # Default 1 hour duration
    
    ics_content = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//DYP COET//Event Calendar//EN
BEGIN:VEVENT
UID:{event_data['id']}@dypcoet.edu
DTSTAMP:{datetime.now().strftime('%Y%m%dT%H%M%S')}Z
DTSTART:{event_date.strftime('%Y%m%dT%H%M%S')}Z
DTEND:{end_date.strftime('%Y%m%dT%H%M%S')}Z
SUMMARY:{event_data['title']}
DESCRIPTION:{event_data.get('description', '')}
LOCATION:{event_data.get('location', 'DYP COET')}
END:VEVENT
END:VCALENDAR"""
    
    return Response(
        ics_content,
        mimetype='text/calendar',
        headers={
            'Content-Disposition': f'attachment; filename=event_{event_data["id"]}.ics'
        }
    )
