from datetime import datetime, timedelta
import time
import json

# Add these routes to your existing app.py

@app.route('/api/upcoming-events')
@login_required
def get_upcoming_events():
    """Get upcoming events for the strip"""
    # Get events from now onwards
    now = datetime.now()
    upcoming_events = Event.query.filter(Event.date >= now).order_by(Event.date).limit(10).all()
    
    # Get all clubs for reference
    clubs = Club.query.all()
    
    events_data = []
    for event in upcoming_events:
        # Convert datetime to nanoseconds timestamp for JS compatibility
        event_date_nano = int(event.date.timestamp() * 1_000_000_000)
        
        # Find club if exists
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

@app.route('/api/event/download-ics', methods=['POST'])
@login_required
def download_event_ics():
    """Generate and download ICS file for event"""
    event_data = request.json
    if not event_data:
        return jsonify({'error': 'Event data required'}), 400
    
    # Create ICS content
    event_date = datetime.fromtimestamp(event_data['eventDate'] / 1_000_000_000)
    end_date = event_date + timedelta(hours=2)  # Default 2 hour duration
    
    # Escape special characters for ICS
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
