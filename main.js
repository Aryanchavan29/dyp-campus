// Initialize tooltips and popovers
document.addEventListener('DOMContentLoaded', function() {
    // Enable tooltips
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function(tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // Enable popovers
    var popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
    popoverTriggerList.map(function(popoverTriggerEl) {
        return new bootstrap.Popover(popoverTriggerEl);
    });

    // Add floating animation to elements
    addFloatingAnimation();
    
    // Initialize AJAX handlers
    initAjaxHandlers();
});

// Floating animation for background elements
function addFloatingAnimation() {
    const elements = document.querySelectorAll('.floating-element');
    elements.forEach((el, index) => {
        el.style.animation = `float ${6 + index}s ease-in-out infinite`;
    });
}

// AJAX Handlers
function initAjaxHandlers() {
    // Course enrollment
    document.querySelectorAll('.enroll-btn').forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            const courseId = this.dataset.courseId;
            enrollInCourse(courseId, this);
        });
    });

    // Event registration
    document.querySelectorAll('.event-register-btn').forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            const eventId = this.dataset.eventId;
            registerForEvent(eventId, this);
        });
    });

    // Join club
    document.querySelectorAll('.join-club-btn').forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            const clubId = this.dataset.clubId;
            joinClub(clubId, this);
        });
    });

    // Create post
    const postForm = document.getElementById('createPostForm');
    if (postForm) {
        postForm.addEventListener('submit', function(e) {
            e.preventDefault();
            createPost();
        });
    }

    // Like post
    document.querySelectorAll('.like-btn').forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            const postId = this.dataset.postId;
            likePost(postId, this);
        });
    });
}

// Course enrollment function
function enrollInCourse(courseId, btnElement) {
    const originalText = btnElement.innerHTML;
    btnElement.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Enrolling...';
    btnElement.disabled = true;

    fetch(`/enroll/${courseId}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showNotification('Success!', data.message, 'success');
            btnElement.innerHTML = '<i class="fas fa-check-circle me-2"></i>Enrolled';
            btnElement.classList.remove('btn-primary');
            btnElement.classList.add('btn-success');
        } else {
            showNotification('Error!', data.message, 'danger');
            btnElement.innerHTML = originalText;
            btnElement.disabled = false;
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showNotification('Error!', 'Something went wrong', 'danger');
        btnElement.innerHTML = originalText;
        btnElement.disabled = false;
    });
}

// Event registration function
function registerForEvent(eventId, btnElement) {
    const originalText = btnElement.innerHTML;
    btnElement.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Registering...';
    btnElement.disabled = true;

    fetch(`/register_event/${eventId}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showNotification('Success!', data.message, 'success');
            btnElement.innerHTML = '<i class="fas fa-check-circle me-2"></i>Registered';
            btnElement.classList.remove('btn-primary');
            btnElement.classList.add('btn-success');
        } else {
            showNotification('Error!', data.message, 'danger');
            btnElement.innerHTML = originalText;
            btnElement.disabled = false;
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showNotification('Error!', 'Something went wrong', 'danger');
        btnElement.innerHTML = originalText;
        btnElement.disabled = false;
    });
}

// Join club function
function joinClub(clubId, btnElement) {
    const originalText = btnElement.innerHTML;
    btnElement.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Joining...';
    btnElement.disabled = true;

    fetch(`/join_club/${clubId}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showNotification('Success!', data.message, 'success');
            btnElement.innerHTML = '<i class="fas fa-check-circle me-2"></i>Member';
            btnElement.classList.remove('btn-primary');
            btnElement.classList.add('btn-success');
        } else {
            showNotification('Error!', data.message, 'danger');
            btnElement.innerHTML = originalText;
            btnElement.disabled = false;
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showNotification('Error!', 'Something went wrong', 'danger');
        btnElement.innerHTML = originalText;
        btnElement.disabled = false;
    });
}

// Create post function
function createPost() {
    const content = document.getElementById('postContent').value;
    if (!content.trim()) {
        showNotification('Error!', 'Post content cannot be empty', 'warning');
        return;
    }

    const formData = new FormData();
    formData.append('content', content);

    fetch('/create_post', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            document.getElementById('postContent').value = '';
            showNotification('Success!', 'Post created successfully', 'success');
            // Add new post to feed without reload
            addPostToFeed(data.post);
        } else {
            showNotification('Error!', data.message, 'danger');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showNotification('Error!', 'Something went wrong', 'danger');
    });
}

// Add new post to feed dynamically
function addPostToFeed(post) {
    const postsFeed = document.getElementById('postsFeed');
    const postHtml = `
        <div class="card mb-3 border-0 shadow-sm rounded-4 animate__animated animate__fadeInUp">
            <div class="card-body">
                <div class="d-flex mb-3">
                    <div class="flex-shrink-0">
                        <i class="fas fa-user-circle fa-3x text-primary"></i>
                    </div>
                    <div class="flex-grow-1 ms-3">
                        <h6 class="mb-0">${post.author}</h6>
                        <small class="text-muted">Just now</small>
                    </div>
                </div>
                <p class="mb-3">${post.content}</p>
                <div class="d-flex">
                    <button class="btn btn-sm btn-outline-primary me-2 like-btn" data-post-id="${post.id}">
                        <i class="far fa-heart me-1"></i>Like <span class="like-count">0</span>
                    </button>
                    <button class="btn btn-sm btn-outline-secondary">
                        <i class="far fa-comment me-1"></i>Comment
                    </button>
                </div>
            </div>
        </div>
    `;
    postsFeed.insertAdjacentHTML('afterbegin', postHtml);
    
    // Add event listener to new like button
    const newLikeBtn = document.querySelector(`[data-post-id="${post.id}"]`);
    if (newLikeBtn) {
        newLikeBtn.addEventListener('click', function(e) {
            e.preventDefault();
            likePost(post.id, this);
        });
    }
}

// Like post function
function likePost(postId, btnElement) {
    const likeCountSpan = btnElement.querySelector('.like-count');
    const currentLikes = parseInt(likeCountSpan.textContent);

    fetch(`/like_post/${postId}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            likeCountSpan.textContent = data.likes;
            btnElement.innerHTML = `<i class="fas fa-heart text-danger me-1"></i>Like <span class="like-count">${data.likes}</span>`;
            btnElement.classList.add('liked');
        }
    })
    .catch(error => {
        console.error('Error:', error);
    });
}

// Notification system
function showNotification(title, message, type = 'info') {
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `alert alert-${type} alert-dismissible fade show position-fixed top-0 end-0 m-3`;
    notification.style.zIndex = '9999';
    notification.style.maxWidth = '400px';
    notification.innerHTML = `
        <strong>${title}</strong> ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    document.body.appendChild(notification);
    
    // Auto dismiss after 3 seconds
    setTimeout(() => {
        notification.classList.remove('show');
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

// Calendar view toggle
const gridViewBtn = document.getElementById('gridView');
const calendarViewBtn = document.getElementById('calendarView');
if (gridViewBtn && calendarViewBtn) {
    gridViewBtn.addEventListener('click', function() {
        document.getElementById('eventsGridView').classList.remove('d-none');
        document.getElementById('eventsCalendarView').classList.add('d-none');
        this.classList.add('active');
        calendarViewBtn.classList.remove('active');
    });

    calendarViewBtn.addEventListener('click', function() {
        document.getElementById('eventsGridView').classList.add('d-none');
        document.getElementById('eventsCalendarView').classList.remove('d-none');
        this.classList.add('active');
        gridViewBtn.classList.remove('active');
        
        // Load calendar events if not already loaded
        if (!window.calendarInitialized) {
            initializeCalendar();
        }
    });
}

// Initialize full calendar (requires additional library)
function initializeCalendar() {
    // This would integrate with a calendar library like FullCalendar
    console.log('Calendar initialized');
    window.calendarInitialized = true;
}

// Smooth scroll for anchor links
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
        e.preventDefault();
        const target = document.querySelector(this.getAttribute('href'));
        if (target) {
            target.scrollIntoView({
                behavior: 'smooth',
                block: 'start'
            });
        }
    });
});

// Parallax effect on scroll
window.addEventListener('scroll', function() {
    const scrolled = window.pageYOffset;
    const parallaxElements = document.querySelectorAll('.parallax');
    
    parallaxElements.forEach(element => {
        const speed = element.dataset.speed || 0.5;
        element.style.transform = `translateY(${scrolled * speed}px)`;
    });
});

// Form validation
(function() {
    'use strict';
    
    const forms = document.querySelectorAll('.needs-validation');
    
    Array.from(forms).forEach(form => {
        form.addEventListener('submit', event => {
            if (!form.checkValidity()) {
                event.preventDefault();
                event.stopPropagation();
            }
            
            form.classList.add('was-validated');
        }, false);
    });
})();

// Password visibility toggle
document.querySelectorAll('.toggle-password').forEach(button => {
    button.addEventListener('click', function() {
        const input = this.previousElementSibling;
        const type = input.getAttribute('type') === 'password' ? 'text' : 'password';
        input.setAttribute('type', type);
        this.querySelector('i').classList.toggle('fa-eye');
        this.querySelector('i').classList.toggle('fa-eye-slash');
    });
});

// Animate on scroll
const observerOptions = {
    threshold: 0.1,
    rootMargin: '0px 0px -50px 0px'
};

const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            entry.target.classList.add('animate__animated', 'animate__fadeInUp');
            observer.unobserve(entry.target);
        }
    });
}, observerOptions);

document.querySelectorAll('.card, .course-card, .event-card').forEach(el => {
    observer.observe(el);
});
