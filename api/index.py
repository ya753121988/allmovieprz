from flask import Flask, render_template_string, request, redirect, url_for, flash, jsonify, session
from functools import wraps
from pymongo import MongoClient
from bson.objectid import ObjectId
import requests
import os
import json
import time 
import re 
from urllib.parse import unquote  

app = Flask(__name__)
app.secret_key = "dooplay_ultra_pro_max_secret"

# ==========================================
# MongoDB Database Connection & Optimization
# ==========================================
MONGO_URI = "mongodb+srv://Akash:Akash@cluster0.n8ngrpu.mongodb.net/?appName=Cluster0"
client = MongoClient(MONGO_URI)
db = client['movie_website']

movies_col = db['movies']
options_col = db['options']

# 🚀 NEW FEATURE: CUSTOM DOMAIN (TENANT) DATABASE
domains_col = db['domains'] 

# 100M+ Traffic Handling: Creating Indexes for Zero-Second DB Query
try:
    movies_col.create_index([("type", 1), ("_id", -1)])
    movies_col.create_index([("categories", 1), ("_id", -1)])
    movies_col.create_index([("views", -1)])
    movies_col.create_index([("title", "text")])
    domains_col.create_index([("host", 1)])
except Exception as e:
    pass

# ==========================================
# 🚀 AUTO SETUP MAIN ADMIN & DOMAIN SYSTEM
# ==========================================
if domains_col.count_documents({}) == 0:
    old_settings = db['settings'].find_one({"type": "general"}) or {}
    old_settings.pop('_id', None)
    old_settings.pop('type', None)
    admin_user = old_settings.pop('admin_user', 'admin')
    admin_pass = old_settings.pop('admin_pass', 'admin')
    
    # Create the Master Admin Tenant
    domains_col.insert_one({
        "host": "main", # Default wildcard for Main Server Domain
        "is_main": True,
        "admin_user": admin_user,
        "admin_pass": admin_pass,
        "expire_at": 20000000000, # Never expires
        "price_paid": 0,
        "settings": old_settings if old_settings else {
            "ad_status_banner": "off",
            "ad_status_direct": "off",
            "limits": {"Movie": "12", "Series": "12", "Drama": "12", "Anime": "12", "Episode": "12"}
        }
    })

# Identify which Custom Domain (.com/.xyz) the user is visiting
def get_tenant():
    host = request.host.split(':')[0]
    t = domains_col.find_one({"host": host})
    if t: return t
    return domains_col.find_one({"is_main": True})

# ==========================================
# High Traffic In-Memory Cache System (Isolated for Domains)
# ==========================================
CACHE_STORE = {}
CACHE_TIMEOUT = 120 

def get_cached_data(key, host):
    full_key = f"{host}_{key}"
    if full_key in CACHE_STORE and (time.time() - CACHE_STORE[full_key]['time']) < CACHE_TIMEOUT:
        return CACHE_STORE[full_key]['data']
    return None

def set_cached_data(key, host, data):
    full_key = f"{host}_{key}"
    CACHE_STORE[full_key] = {'time': time.time(), 'data': data}

def clear_cache():
    global CACHE_STORE
    CACHE_STORE = {}

# ==========================================
# Admin Authentication Decorator (Separated by Domain)
# ==========================================
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        tenant = get_tenant()
        if 'logged_in' not in session or session.get('tenant_host') != tenant.get('host'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

def render_frontend(html, page_name, **kwargs):
    tenant = get_tenant()
    # 🚀 EXPIRE LOCK CHECK: If domain is expired, lock the site details
    is_locked = not tenant.get('is_main') and tenant.get('expire_at', 0) < time.time()
    settings = tenant.get('settings', {})
    return render_template_string(html, is_locked=str(is_locked), settings=settings, page_name=page_name, db=db, **kwargs)

def render_admin(html, **kwargs):
    tenant = get_tenant()
    return render_template_string(html, is_main=tenant.get('is_main', False), db=db, **kwargs)

# ==========================================
# HTML Templates - FRONTEND (User Side)
# ==========================================
FRONTEND_HTML = """
<!DOCTYPE html>
<html lang="en" data-bs-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>DooPlay Pro - Movie Site</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    
    <script>
        document.addEventListener('keydown', function(event) {
            if (event.ctrlKey && (event.key === '=' || event.key === '-' || event.key === '0')) {
                event.preventDefault();
            }
        });
        document.addEventListener('wheel', function(event) {
            if (event.ctrlKey) {
                event.preventDefault();
            }
        }, { passive: false });
    </script>
    
    <style>
        body { background-color: #0b0f19; color: #fff; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; overflow-x: hidden; touch-action: manipulation; }
        .navbar { background-color: #151b2b; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
        .search-bar { max-width: 500px; width: 100%; flex: 1; }
        
        .movie-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; padding: 15px 0; width: 100%; }
        @media (min-width: 576px) { .movie-grid { grid-template-columns: repeat(3, 1fr); } }
        @media (min-width: 768px) { .movie-grid { grid-template-columns: repeat(4, 1fr); gap: 15px; } }
        @media (min-width: 992px) { .movie-grid { grid-template-columns: repeat(5, 1fr); } }
        @media (min-width: 1200px) { .movie-grid { grid-template-columns: repeat(6, 1fr); } }
        @media (min-width: 1400px) { .movie-grid { grid-template-columns: repeat(7, 1fr); } }
        
        .episode-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; padding: 15px 0; width: 100%; }
        @media (min-width: 576px) { .episode-grid { grid-template-columns: repeat(4, 1fr); gap: 10px; } }
        @media (min-width: 992px) { .episode-grid { grid-template-columns: repeat(6, 1fr); gap: 15px; } }

        .movie-card { background: #1e2738; border-radius: 8px; overflow: hidden; display: flex; flex-direction: column; height: 100%; border: 1px solid #2d3748; transition: box-shadow 0.3s ease; }
        .movie-card:hover { box-shadow: 0 8px 15px rgba(0,123,255,0.3); }
        
        .poster-wrapper { position: relative; width: 100%; aspect-ratio: 2/3; overflow: hidden; border-bottom: 1px solid #2d3748; }
        .poster-wrapper-landscape { position: relative; width: 100%; aspect-ratio: 16/9; overflow: hidden; border-bottom: 1px solid #2d3748; }
        .movie-poster { width: 100%; height: 100%; object-fit: cover; }
        
        .movie-badge { position: absolute; top: 8px; right: 8px; background: #e50914; color: #fff; padding: 3px 8px; font-size: 11px; border-radius: 4px; font-weight: bold; z-index: 2; box-shadow: 0 2px 4px rgba(0,0,0,0.5);}
        .movie-quality { position: absolute; top: 8px; left: 8px; background: #007bff; color: #fff; padding: 3px 8px; font-size: 11px; border-radius: 4px; font-weight: bold; z-index: 2; box-shadow: 0 2px 4px rgba(0,0,0,0.5);}
        .movie-views { position: absolute; bottom: 8px; left: 8px; background: rgba(0,0,0,0.85); color: #fff; padding: 3px 8px; font-size: 11px; border-radius: 4px; z-index: 2; border: 1px solid #333; }
        
        .movie-info { padding: 10px 8px; text-align: center; flex-grow: 1; display: flex; flex-direction: column; justify-content: center; background: #1e2738; }
        .movie-title { font-size: 14px; font-weight: 600; color: #e2e8f0; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; line-height: 1.3; margin-bottom: 6px; }
        .movie-meta { font-size: 11px; color: #8c98a4; display: flex; flex-wrap: wrap; justify-content: center; align-items: center; gap: 4px; }
        
        .episodes-grid { display: flex; flex-direction: column; gap: 10px; max-height: 500px; overflow-y: auto; overflow-x: hidden; padding-right: 5px; padding-bottom: 12px; scrollbar-width: thin; }
        .ep-box { background: #151b2b; padding: 10px; border-radius: 8px; border-left: 4px solid #007bff; width: 100%; display: flex; flex-direction: column; justify-content: start; border: 1px solid #1e2738; }
        
        .nav-pills .nav-link { background: #1e2738; color: #fff; border: 1px solid #2d3748; padding: 8px 20px; }
        .nav-pills .nav-link.active { background: #007bff; color: #fff; border-color: #007bff; box-shadow: 0 4px 6px rgba(0,123,255,0.3); }

        .cat-scroll { display: flex; overflow-x: auto; gap: 10px; padding: 10px 0; }
        .cat-scroll::-webkit-scrollbar { display: none; }
        .cat-badge { background: #1e2738; color: #fff; padding: 5px 15px; border-radius: 20px; text-decoration: none; font-size: 13px; border: 1px solid #2d3748; white-space: nowrap;}
        .cat-badge:hover { background: #007bff; }
        
        .carousel-caption { background: linear-gradient(0deg, rgba(11,15,25,1) 0%, rgba(11,15,25,0.6) 50%, rgba(0,212,255,0) 100%); bottom: 0; left: 0; right: 0; padding-bottom: 20px; }
        
        .promo-box { border-radius: 8px; overflow: hidden; border: 1px solid #ffc107; transition: 0.3s; background-color: #1e2738; }
        .promo-box:hover { box-shadow: 0 0 15px rgba(255, 193, 7, 0.5); }
        .promo-img { width: 100%; aspect-ratio: 16/9; object-fit: contain; background: #000; border-bottom: 1px solid #ffc107; }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark sticky-top">
        <div class="container-fluid px-3 px-md-5 d-flex flex-wrap align-items-center justify-content-between">
            <a class="navbar-brand fw-bold me-auto fs-4" href="/"><i class="fas fa-play text-primary"></i> DooPlay</a>
            <form action="/search" method="GET" class="d-flex search-bar mx-2 mx-lg-auto order-3 order-lg-2 mt-2 mt-lg-0 w-100">
                <input class="form-control me-2 bg-dark text-white border-secondary" type="search" name="q" placeholder="Search Movies, Series..." required>
                <button class="btn btn-primary px-4" type="submit"><i class="fas fa-search"></i></button>
            </form>
            <button class="navbar-toggler ms-2 order-2 order-lg-3" type="button" data-bs-toggle="collapse" data-bs-target="#navMenu">
                <span class="navbar-toggler-icon"></span>
            </button>
            <div class="collapse navbar-collapse order-4" id="navMenu" style="flex-grow: 0;">
                <ul class="navbar-nav ms-auto mt-3 mt-lg-0" style="max-height: 350px; overflow-y: auto; overflow-x: hidden;">
                    {% set nav_cats = db.options.find({"type": "category"}) %}
                    <li class="nav-item"><a class="nav-link text-white fw-bold" href="/"><i class="fas fa-home text-primary"></i> Home</a></li>
                    {% for c in nav_cats %}
                    <li class="nav-item"><a class="nav-link text-white" href="/category/{{ c.value }}"><i class="fas fa-tags text-warning"></i> {{ c.value }}</a></li>
                    {% endfor %}
                </ul>
            </div>
        </div>
    </nav>
    
    <div class="container-fluid px-3 px-md-5 mt-3">
        {% if settings.get('ad_header') %}
            <div class="w-100 text-center mb-3">{{ settings.get('ad_header') | safe }}</div>
        {% endif %}

        {% if settings.get('notice') %}
            <div class="alert alert-info text-center shadow-sm rounded border-primary border-start border-4" style="background:#1e2738; color:#fff;">
                <i class="fas fa-bell text-warning"></i> {{ settings.get('notice') }}
            </div>
        {% endif %}
        
        {% if settings.get('ad_status_banner') == 'on' %}
            {% if settings.get('ad_banner_popular') %}
                <div class="text-center mb-3 ad-box w-100">
                    <div style="font-size: 11px; color: #8c98a4; margin-bottom: 2px;">- Popular Advertisement -</div>
                    {{ settings.get('ad_banner_popular') | safe }}
                </div>
            {% endif %}

            {% if page_name in ['home', 'search', 'category'] %}
                <div class="d-none d-md-block text-center mb-3 ad-box">{{ settings.get('ad_banner_home_desktop') | safe }}</div>
                <div class="d-block d-md-none text-center mb-3 ad-box">{{ settings.get('ad_banner_home_mobile') | safe }}</div>
            {% elif page_name == 'detail' %}
                <div class="d-none d-md-block text-center mb-3 ad-box">{{ settings.get('ad_banner_detail_desktop') | safe }}</div>
                <div class="d-block d-md-none text-center mb-3 ad-box">{{ settings.get('ad_banner_detail_mobile') | safe }}</div>
            {% endif %}
        {% endif %}
    </div>

    <!-- MAIN FLUID CONTAINER -->
    <div class="container-fluid px-3 px-md-5 pb-5">
        <!-- CONTENT_BLOCK -->
        
        {% if settings.get('ad_footer') %}
            <div class="w-100 text-center mt-5 mb-2">{{ settings.get('ad_footer') | safe }}</div>
        {% endif %}
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    
    <!-- 🚀 NEW FEATURE: 0-SECOND DIRECT REDIRECT & EXPIRE LOCK SYSTEM -->
    <script>
        const isLocked = "{{ is_locked }}"; // Checks if Custom Domain is Expired
        const adStatusDirect = "{{ settings.get('ad_status_direct', 'off') }}";
        const rawLinks = '{{ settings.get("direct_links", []) | tojson | safe }}';
        let directLinks = [];
        try { directLinks = JSON.parse(rawLinks); } catch(e) {}
        
        let adClickIndex = parseInt(localStorage.getItem('dooplay_ad_index')) || 0;

        function handleMovieClick(event, url) {
            // Check if Domain Expired
            if(isLocked === 'True') {
                event.preventDefault();
                alert('⚠️ এই ডোমেনটির সাবস্ক্রিপশন মেয়াদ শেষ হয়ে গেছে! দয়া করে মেইন এডমিনের সাথে যোগাযোগ করুন।');
                return;
            }
            
            // 0-Second Redirect System (NO LOADER)
            if(adStatusDirect === 'on' && directLinks.length > 0) {
                event.preventDefault(); 
                let clickUrl = directLinks[adClickIndex % directLinks.length];
                adClickIndex++;
                localStorage.setItem('dooplay_ad_index', adClickIndex);
                window.open(clickUrl, '_blank'); 
                window.location.href = url; // Instant redirect
            } else {
                // Let native browser click happen instantly (0 Second Delay)
            }
        }

        // Check Ad for download/watch link buttons
        function checkAd(event, url) {
            if(adStatusDirect === 'on' && directLinks.length > 0) {
                event.preventDefault();
                let clickUrl = directLinks[adClickIndex % directLinks.length];
                adClickIndex++;
                localStorage.setItem('dooplay_ad_index', adClickIndex);
                window.open(clickUrl, '_blank'); 
                window.location.href = url; 
            }
        }
    </script>
</body>
</html>
"""

# ==========================================
# HTML Templates - ADMIN (Backend)
# ==========================================
ADMIN_HTML = """
<!DOCTYPE html>
<html lang="en" data-bs-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Admin Panel - DooPlay Pro</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    
    <script>
        document.addEventListener('keydown', function(event) {
            if (event.ctrlKey && (event.key === '=' || event.key === '-' || event.key === '0')) {
                event.preventDefault();
            }
        });
        document.addEventListener('wheel', function(event) {
            if (event.ctrlKey) {
                event.preventDefault();
            }
        }, { passive: false });
    </script>
    
    <style>
        body { background-color: #0b0f19; color: #fff; font-family: 'Segoe UI', sans-serif; touch-action: manipulation; }
        .sidebar { min-height: 100vh; background-color: #151b2b; padding-top: 20px; border-right: 1px solid #2d3748; }
        .sidebar a { color: #8c98a4; text-decoration: none; padding: 15px 20px; display: block; font-weight: 500; transition: 0.3s; font-size: 15px; }
        .sidebar a:hover, .sidebar a.active { background-color: #1e2738; color: #007bff; border-left: 4px solid #007bff; }
        .content { padding: 30px; }
        .card { background-color: #151b2b; border: 1px solid #2d3748; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.2); }
        .form-control, .form-select { background-color: #0b0f19; border: 1px solid #3b475c; color: #fff; }
        .form-control:focus, .form-select:focus { border-color: #007bff; background-color: #0b0f19; color: #fff; box-shadow: 0 0 5px rgba(0,123,255,0.5); }
    </style>
</head>
<body>
    <div class="container-fluid">
        <div class="row">
            <div class="col-md-2 sidebar d-none d-md-block">
                <h4 class="text-center text-white mb-4 fw-bold"><i class="fas fa-play text-primary"></i> Admin Pro</h4>
                <a href="/admin"><i class="fas fa-tachometer-alt me-2"></i> ড্যাশবোর্ড</a>
                
                <!-- 🚀 NEW FEATURE: ONLY MAIN ADMIN SEES DOMAINS MENU -->
                {% if is_main %}
                <a href="/admin/domains" style="color: #ffc107;"><i class="fas fa-globe me-2"></i> 🌐 কাস্টম ডোমেন এড</a>
                {% endif %}
                
                <a href="/admin/add_movie"><i class="fas fa-plus-circle me-2"></i> মুভি/সিরিজ এড</a>
                <a href="/admin/all_movies"><i class="fas fa-list me-2"></i> অল মুভি ও ডিলেট</a>
                <a href="/admin/options"><i class="fas fa-tags me-2"></i> ব্যাজ/ক্যাটাগরি এড</a>
                <a href="/admin/settings"><i class="fas fa-cog me-2"></i> সেটিংস ও এডস</a>
                <a href="/" target="_blank"><i class="fas fa-external-link-alt me-2"></i> সাইট দেখুন</a>
                <a href="/logout" class="text-danger mt-5"><i class="fas fa-sign-out-alt me-2"></i> লগআউট</a>
            </div>
            
            <div class="col-12 d-md-none bg-dark p-3 d-flex justify-content-between align-items-center mb-3 border-bottom border-secondary">
                <h5 class="m-0 fw-bold"><i class="fas fa-play text-primary"></i> Admin Pro</h5>
                <select class="form-select w-50" onchange="location = this.value;">
                    <option value="/admin">ড্যাশবোর্ড</option>
                    {% if is_main %}
                    <option value="/admin/domains">🌐 কাস্টম ডোমেন এড</option>
                    {% endif %}
                    <option value="/admin/add_movie">মুভি এড</option>
                    <option value="/admin/all_movies">অল মুভি</option>
                    <option value="/admin/options">ব্যাজ/ক্যাটাগরি</option>
                    <option value="/admin/settings">সেটিংস</option>
                    <option value="/">সাইট দেখুন</option>
                    <option value="/logout">লগআউট</option>
                </select>
            </div>

            <div class="col-md-10 content">
                {% if get_flashed_messages() %}
                    {% for msg in get_flashed_messages() %}
                        <div class="alert alert-success alert-dismissible fade show" style="background:#198754; color:#fff; border:none;">
                            <i class="fas fa-check-circle"></i> {{ msg }} 
                            <button type="button" class="btn-close btn-close-white" data-bs-dismiss="alert"></button>
                        </div>
                    {% endfor %}
                {% endif %}
                
                <!-- CONTENT_BLOCK -->
                
            </div>
        </div>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <!-- SCRIPTS_BLOCK -->
</body>
</html>
"""

# ==========================================
# PUBLIC ROUTES (Frontend)
# ==========================================

@app.route('/')
def home():
    tenant = get_tenant()
    host = tenant.get('host')
    
    # Cache System for high traffic (100M Users)
    cached_html = get_cached_data('home_page', host)
    if cached_html:
        return cached_html

    settings = tenant.get('settings', {})
    limits = settings.get('limits', {})
    promos = settings.get('promos', [])
    
    top_slider = list(movies_col.find().sort('views', -1).limit(5))
    
    # Auto Dynamic Categories Extraction
    active_types = movies_col.distinct("type")
    all_types = list(set(active_types + ["Movie", "Series", "Drama", "Anime"]))
    ordered_types = ["Movie", "Series", "Episode", "Anime"]
    other_types = [t for t in all_types if t not in ordered_types and t != "Episode"]
    
    sections = {}
    for t in all_types:
        if t != "Episode":
            lim = int(limits.get(t, 12))
            items = list(movies_col.find({"type": t}).sort('_id', -1).limit(lim))
            if items:
                sections[t] = items
    
    # LATEST EPISODES EXTRACTION
    lim_e = int(limits.get('Episode', 12))
    latest_episodes = []
    recent_series_dramas = list(movies_col.find({"type": {"$in": ["Series", "Drama", "Anime"]}}).sort('_id', -1).limit(20))
    for s_obj in recent_series_dramas:
        for season in reversed(s_obj.get('seasons', [])):
            for ep in reversed(season.get('episodes', [])):
                ep_copy = ep.copy()
                ep_copy['series_title'] = s_obj['title']
                ep_copy['series_id'] = str(s_obj['_id'])
                ep_copy['season_num'] = season['season']
                ep_copy['m_backdrop'] = s_obj.get('backdrop')
                ep_copy['m_poster'] = s_obj.get('poster')
                ep_copy['m_badge'] = s_obj.get('badge')
                latest_episodes.append(ep_copy)
                if len(latest_episodes) >= lim_e: break
            if len(latest_episodes) >= lim_e: break
        if len(latest_episodes) >= lim_e: break

    categories = list(options_col.find({"type": "category"}))
    
    promo_html = """
    {% if promos %}
    <div class="row my-4">
        {% for p in promos %}
        <div class="col-6 col-md-4 col-lg-3 col-xl-2 mb-3">
            <a href="{{ p.url }}" target="_blank" class="text-decoration-none">
                <div class="promo-box text-center h-100 d-flex flex-column justify-content-between">
                    <img src="{{ p.image }}" class="promo-img" alt="Promo">
                    <div class="p-2">
                        <span class="text-warning fw-bold small"><i class="fas fa-star"></i> {{ p.text }}</span>
                    </div>
                </div>
            </a>
        </div>
        {% endfor %}
    </div>
    {% endif %}
    """

    html = FRONTEND_HTML.replace('<!-- CONTENT_BLOCK -->', """
    <div class="cat-scroll mb-3">
        <a href="/" class="cat-badge bg-primary text-white">All</a>
        {% for c in categories %}
            <a href="/category/{{ c.value }}" class="cat-badge">{{ c.value }}</a>
        {% endfor %}
    </div>

    <!-- 1. TOP MOVIE SLIDER WITH LANDSCAPE POSTER FIX -->
    <div id="topMoviesCarousel" class="carousel slide mb-4 rounded overflow-hidden shadow-lg border border-secondary" data-bs-ride="carousel">
        <div class="carousel-inner">
            {% for m in top_slider %}
            <div class="carousel-item {% if loop.first %}active{% endif %}">
                <a href="/movie/{{ m._id }}" onclick="handleMovieClick(event, this.href)">
                    <!-- FIX: aspect-ratio ensures 100% visibility on all devices without crop -->
                    <div style="width: 100%; aspect-ratio: 16/9; max-height: 500px; background: url('{{ m.backdrop or m.poster }}') center/cover no-repeat; position: relative;">
                        <div class="carousel-caption text-start px-md-5 pb-md-5">
                            <h2 class="fw-bold text-white shadow-sm" style="text-shadow: 2px 2px 4px rgba(0,0,0,0.8);">{{ m.title }}</h2>
                            <span class="badge bg-danger px-3 py-2 fs-6">{{ m.type }}</span>
                            <span class="badge bg-primary px-3 py-2 fs-6"><i class="fas fa-eye"></i> {{ m.views }} Views</span>
                        </div>
                    </div>
                </a>
            </div>
            {% endfor %}
        </div>
        <button class="carousel-control-prev" type="button" data-bs-target="#topMoviesCarousel" data-bs-slide="prev">
            <span class="carousel-control-prev-icon" aria-hidden="true" style="width: 3rem; height: 3rem;"></span>
        </button>
        <button class="carousel-control-next" type="button" data-bs-target="#topMoviesCarousel" data-bs-slide="next">
            <span class="carousel-control-next-icon" aria-hidden="true" style="width: 3rem; height: 3rem;"></span>
        </button>
    </div>
    
    """ + promo_html + """

    <!-- 2. MOVIES SECTION -->
    {% if sections.get('Movie') %}
    <div class="d-flex justify-content-between align-items-center mt-5 mb-3 border-start border-primary border-4 ps-3">
        <h3 class="fw-bold text-uppercase m-0 text-primary">Latest Movies</h3>
        <a href="/category/Movie" class="btn btn-outline-primary fw-bold px-4">View All</a>
    </div>
    <div class="movie-grid">
        {% for m in sections.get('Movie') %}
        <a href="/movie/{{ m._id }}" class="text-decoration-none" onclick="handleMovieClick(event, this.href)">
            <div class="movie-card">
                <div class="poster-wrapper">
                    {% if m.badge %}<span class="movie-badge">{{ m.badge }}</span>{% endif %}
                    {% if m.quality %}<span class="movie-quality">{{ m.quality }}</span>{% endif %}
                    <span class="movie-views"><i class="fas fa-eye"></i> {{ m.views | default(0) }}</span>
                    <img src="{{ m.poster }}" alt="{{ m.title }}" class="movie-poster" onerror="this.src='https://via.placeholder.com/300x450?text=No+Poster'">
                </div>
                <div class="movie-info">
                    <div class="movie-title fs-6">{{ m.title }}</div>
                    <div class="movie-meta">
                        <span class="text-warning fw-bold">{{ m.type }}</span>
                        {% if m.date %} <span class="ms-1">• {{ m.date[:4] }}</span> {% endif %}
                    </div>
                </div>
            </div>
        </a>
        {% endfor %}
    </div>
    """ + promo_html + """
    {% endif %}

    <!-- 3. SERIES SECTION -->
    {% if sections.get('Series') %}
    <div class="d-flex justify-content-between align-items-center mt-5 mb-3 border-start border-success border-4 ps-3">
        <h3 class="fw-bold text-uppercase m-0 text-success">Latest Series</h3>
        <a href="/category/Series" class="btn btn-outline-success fw-bold px-4">View All</a>
    </div>
    <div class="movie-grid">
        {% for m in sections.get('Series') %}
        <a href="/movie/{{ m._id }}" class="text-decoration-none" onclick="handleMovieClick(event, this.href)">
            <div class="movie-card" style="border-color: #198754;">
                <div class="poster-wrapper">
                    {% if m.badge %}<span class="movie-badge">{{ m.badge }}</span>{% endif %}
                    <span class="movie-quality bg-success">Episodes Added</span>
                    <span class="movie-views"><i class="fas fa-eye"></i> {{ m.views | default(0) }}</span>
                    <img src="{{ m.poster }}" alt="{{ m.title }}" class="movie-poster" onerror="this.src='https://via.placeholder.com/300x450?text=No+Poster'">
                </div>
                <div class="movie-info">
                    <div class="movie-title fs-6">{{ m.title }}</div>
                    <div class="movie-meta"><span class="text-success fw-bold">{{ m.type }}</span></div>
                </div>
            </div>
        </a>
        {% endfor %}
    </div>
    """ + promo_html + """
    {% endif %}

    <!-- GLOBAL MIDDLE AD -->
    {% if settings.get('ad_middle') %}
        <div class="w-100 text-center my-4">{{ settings.get('ad_middle') | safe }}</div>
    {% endif %}

    <!-- 4. LATEST EPISODES SECTION (3 IN LINE ON MOBILE) -->
    {% if latest_episodes %}
    <div class="d-flex justify-content-between align-items-center mt-4 mb-3 border-start border-info border-4 ps-3">
        <h3 class="fw-bold text-uppercase m-0 text-info">Latest Episodes</h3>
    </div>
    <div class="episode-grid">
        {% for ep in latest_episodes %}
        <a href="/movie/{{ ep.series_id }}" class="text-decoration-none" onclick="handleMovieClick(event, this.href)">
            <div class="movie-card" style="border-color: #0dcaf0;">
                <div class="poster-wrapper-landscape">
                    {% if ep.m_badge %}<span class="movie-badge">{{ ep.m_badge }}</span>{% endif %}
                    <!-- EPISODE POSTER Fallback sequence -->
                    <img src="{{ ep.poster or ep.m_backdrop or ep.m_poster }}" alt="Episode" class="movie-poster" onerror="this.src='https://via.placeholder.com/600x337?text=No+Poster'">
                </div>
                <!-- Small padding for mobile fit -->
                <div class="movie-info text-start p-2 p-md-3">
                    <div class="movie-title fw-bold text-info mb-1" style="font-size: 11px;">{{ ep.series_title }}</div>
                    <div class="movie-meta justify-content-start">
                        <span class="text-light fw-bold" style="font-size: 10px;">
                            {% if ep.ep_title %}
                                {{ ep.ep_title }} (S{{ "%02d"|format(ep.season_num|int) }} E{{ "%02d"|format(ep.episode|int) }})
                            {% else %}
                                Season {{ "%02d"|format(ep.season_num|int) }} Ep {{ "%02d"|format(ep.episode|int) }}
                            {% endif %}
                        </span>
                    </div>
                </div>
            </div>
        </a>
        {% endfor %}
    </div>
    """ + promo_html + """
    {% endif %}
    
    <!-- 5. ANIME SECTION -->
    {% if sections.get('Anime') %}
    <div class="d-flex justify-content-between align-items-center mt-5 mb-3 border-start border-danger border-4 ps-3">
        <h3 class="fw-bold text-uppercase m-0 text-danger">Latest Anime</h3>
        <a href="/category/Anime" class="btn btn-outline-danger fw-bold px-4">View All</a>
    </div>
    <div class="movie-grid">
        {% for m in sections.get('Anime') %}
        <a href="/movie/{{ m._id }}" class="text-decoration-none" onclick="handleMovieClick(event, this.href)">
            <div class="movie-card" style="border-color: #dc3545;">
                <div class="poster-wrapper">
                    {% if m.badge %}<span class="movie-badge">{{ m.badge }}</span>{% endif %}
                    <span class="movie-views"><i class="fas fa-eye"></i> {{ m.views | default(0) }}</span>
                    <img src="{{ m.poster }}" alt="{{ m.title }}" class="movie-poster" onerror="this.src='https://via.placeholder.com/300x450?text=No+Poster'">
                </div>
                <div class="movie-info">
                    <div class="movie-title fs-6">{{ m.title }}</div>
                    <div class="movie-meta"><span class="text-danger fw-bold">{{ m.type }}</span></div>
                </div>
            </div>
        </a>
        {% endfor %}
    </div>
    """ + promo_html + """
    {% endif %}
    
    <!-- 6. ALL OTHER DYNAMIC SECTIONS (Drama, etc) -->
    {% for t in other_types %}
        {% if sections.get(t) %}
        <div class="d-flex justify-content-between align-items-center mt-5 mb-3 border-start border-warning border-4 ps-3">
            <h3 class="fw-bold text-uppercase m-0 text-warning">Latest {{ t }}</h3>
            <a href="/category/{{ t }}" class="btn btn-outline-warning fw-bold px-4">View All</a>
        </div>
        <div class="movie-grid">
            {% for m in sections.get(t) %}
            <a href="/movie/{{ m._id }}" class="text-decoration-none" onclick="handleMovieClick(event, this.href)">
                <div class="movie-card" style="border-color: #ffc107;">
                    <div class="poster-wrapper">
                        {% if m.badge %}<span class="movie-badge">{{ m.badge }}</span>{% endif %}
                        <span class="movie-views"><i class="fas fa-eye"></i> {{ m.views | default(0) }}</span>
                        <img src="{{ m.poster }}" alt="{{ m.title }}" class="movie-poster" onerror="this.src='https://via.placeholder.com/300x450?text=No+Poster'">
                    </div>
                    <div class="movie-info">
                        <div class="movie-title fs-6">{{ m.title }}</div>
                        <div class="movie-meta"><span class="text-warning fw-bold">{{ m.type }}</span></div>
                    </div>
                </div>
            </a>
            {% endfor %}
        </div>
        """ + promo_html + """
        {% endif %}
    {% endfor %}
    
    {% if not sections and not latest_episodes %}
        <div class="alert alert-secondary text-center mt-5 fs-4">কোনো পোস্ট পাওয়া যায়নি!</div>
    {% endif %}
    """)
    
    rendered_html = render_frontend(html, page_name='home', top_slider=top_slider, sections=sections, latest_episodes=latest_episodes, other_types=other_types, categories=categories, promos=promos)
    set_cached_data('home_page', host, rendered_html) # Save to Custom Domain Cache
    return rendered_html

@app.route('/search')
def search():
    query = request.args.get('q', '')
    movies = list(movies_col.find({"title": {"$regex": query, "$options": "i"}}).sort('_id', -1))
    html = FRONTEND_HTML.replace('<!-- CONTENT_BLOCK -->', """
    <h3 class="mb-4 border-start border-primary border-4 ps-3">Search Results for: <span class="text-warning">{{ query }}</span></h3>
    <div class="movie-grid">
        {% for m in movies %}
        <a href="/movie/{{ m._id }}" class="text-decoration-none" onclick="handleMovieClick(event, this.href)">
            <div class="movie-card">
                <div class="poster-wrapper">
                    {% if m.badge %}<span class="movie-badge">{{ m.badge }}</span>{% endif %}
                    {% if m.quality %}<span class="movie-quality">{{ m.quality }}</span>{% endif %}
                    <span class="movie-views"><i class="fas fa-eye"></i> {{ m.views | default(0) }}</span>
                    <img src="{{ m.poster }}" alt="{{ m.title }}" class="movie-poster" onerror="this.src='https://via.placeholder.com/300x450?text=No+Poster'">
                </div>
                <div class="movie-info">
                    <div class="movie-title">{{ m.title }}</div>
                    <div class="movie-meta">
                        <span class="text-warning fw-bold">{{ m.type }}</span>
                        {% if m.date %} <span class="ms-1">• {{ m.date[:4] }}</span> {% endif %}
                        {% if m.language %} <span class="ms-1">• {{ m.language }}</span> {% endif %}
                    </div>
                </div>
            </div>
        </a>
        {% endfor %}
    </div>
    {% if not movies %}<h4 class="text-center text-muted mt-5">No results found!</h4>{% endif %}
    """)
    return render_frontend(html, page_name='search', movies=movies, query=query)

@app.route('/category/<cat_name>')
def category_filter(cat_name):
    cat_name = unquote(cat_name) 
    tenant = get_tenant()
    host = tenant.get('host')
    
    cache_key = f"cat_{cat_name}"
    cached_html = get_cached_data(cache_key, host)
    if cached_html:
        return cached_html

    active_types = db.movies.distinct("type")
    all_types = list(set(active_types + ["Movie", "Series", "Drama", "Anime"]))
    
    if cat_name in all_types:
        movies = list(movies_col.find({"type": cat_name}).sort('_id', -1))
    else:
        movies = list(movies_col.find({"categories": cat_name}).sort('_id', -1))
    
    categories = list(options_col.find({"type": "category"}))
    html = FRONTEND_HTML.replace('<!-- CONTENT_BLOCK -->', """
    <div class="cat-scroll mb-3">
        <a href="/" class="cat-badge">All</a>
        {% for c in categories %}
            <a href="/category/{{ c.value }}" class="cat-badge {% if cat_name == c.value %}bg-primary{% endif %}">{{ c.value }}</a>
        {% endfor %}
    </div>
    <h3 class="mb-4 border-start border-primary border-4 ps-3">Category: <span class="text-warning">{{ cat_name }}</span></h3>
    <div class="movie-grid">
        {% for m in movies %}
        <a href="/movie/{{ m._id }}" class="text-decoration-none" onclick="handleMovieClick(event, this.href)">
            <div class="movie-card">
                <div class="poster-wrapper">
                    {% if m.badge %}<span class="movie-badge">{{ m.badge }}</span>{% endif %}
                    {% if m.quality %}<span class="movie-quality">{{ m.quality }}</span>{% endif %}
                    <span class="movie-views"><i class="fas fa-eye"></i> {{ m.views | default(0) }}</span>
                    <img src="{{ m.poster }}" alt="{{ m.title }}" class="movie-poster" onerror="this.src='https://via.placeholder.com/300x450?text=No+Poster'">
                </div>
                <div class="movie-info">
                    <div class="movie-title">{{ m.title }}</div>
                    <div class="movie-meta">
                        <span class="text-warning fw-bold">{{ m.type }}</span>
                        {% if m.date %} <span class="ms-1">• {{ m.date[:4] }}</span> {% endif %}
                        {% if m.language %} <span class="ms-1">• {{ m.language }}</span> {% endif %}
                    </div>
                </div>
            </div>
        </a>
        {% endfor %}
    </div>
    """)
    rendered_html = render_frontend(html, page_name='category', movies=movies, cat_name=cat_name, categories=categories)
    set_cached_data(cache_key, host, rendered_html)
    return rendered_html

@app.route('/movie/<id>')
def movie_details(id):
    tenant = get_tenant()
    host = tenant.get('host')
    
    # 🚀 EXPIRE LOCK CHECK FOR DETAIL PAGE
    is_locked = not tenant.get('is_main') and tenant.get('expire_at', 0) < time.time()
    if is_locked:
        return f"<h1 style='color:#ff4444; text-align:center; margin-top:50px; font-family:sans-serif;'>⚠️ ডোমেন ({host}) এর সাবস্ক্রিপশন মেয়াদ শেষ!</h1><h3 style='color:#fff; text-align:center; font-family:sans-serif;'>রেনিউ করতে দয়া করে মেইন এডমিনের সাথে যোগাযোগ করুন।</h3>", 403

    cache_key = f"movie_{id}"
    cached_html = get_cached_data(cache_key, host)
    
    # Update view count asynchronously
    movies_col.update_one({"_id": ObjectId(id)}, {"$inc": {"views": 1}})

    if cached_html:
        return cached_html

    movie = movies_col.find_one({"_id": ObjectId(id)})
    if not movie: return "Not Found", 404
    
    html = FRONTEND_HTML.replace('<!-- CONTENT_BLOCK -->', """
    <div class="row mt-3">
        <!-- FULL WIDTH LANDSCAPE BANNER HEADER FIX -->
        <div class="col-12 mb-3">
            <div class="position-relative w-100 shadow-lg border border-secondary" style="aspect-ratio: 16/9; max-height: 60vh; border-radius: 12px; overflow: hidden; background: url('{{ m.backdrop or m.poster }}') center/cover no-repeat;">
                {% if m.badge %}<span class="movie-badge shadow-lg" style="font-size: 16px; padding: 6px 20px; top: 15px; right: 15px;">{{ m.badge }}</span>{% endif %}
            </div>
        </div>
        
        <!-- TITLE AND TAGS MOVED OUTSIDE POSTER FOR CLEAN VIEW -->
        <div class="col-12 mb-4">
            <h1 class="fw-bold text-white mb-3 mt-2" style="text-shadow: 1px 1px 3px #000;">{{ m.title }}</h1>
            <div class="d-flex flex-wrap gap-2 mb-3">
                <span class="badge bg-danger fs-6 shadow-sm px-3 py-2"><i class="fas fa-video"></i> {{ m.type }}</span>
                {% if m.date %}<span class="badge bg-info text-dark fs-6 shadow-sm px-3 py-2"><i class="far fa-calendar-alt"></i> {{ m.date[:4] }}</span>{% endif %}
                {% if m.quality %}<span class="badge bg-primary fs-6 shadow-sm px-3 py-2">{{ m.quality }}</span>{% endif %}
                {% if m.language %}<span class="badge bg-success fs-6 shadow-sm px-3 py-2"><i class="fas fa-language"></i> {{ m.language }}</span>{% endif %}
                {% for cat in m.categories %}
                    <span class="badge bg-secondary fs-6 shadow-sm px-3 py-2">{{ cat }}</span>
                {% endfor %}
                <span class="badge bg-dark border border-secondary fs-6 shadow-sm px-3 py-2"><i class="fas fa-eye text-primary"></i> Views: {{ m.views }}</span>
            </div>
        </div>
        
        <div class="col-12">
            <p class="text-light p-4 rounded shadow-sm fs-6" style="background: #151b2b; line-height: 1.8; border-left: 5px solid #007bff; border-bottom: 1px solid #2d3748; border-right: 1px solid #2d3748; border-top: 1px solid #2d3748;">{{ m.description }}</p>
            <hr class="border-secondary my-5">
            
            {% if m.type == 'Movie' %}
                <h3 class="mb-4 fw-bold border-start border-warning border-4 ps-3">Download & Watch Links</h3>
                
                <div class="d-flex flex-column gap-3">
                    {% if m.links %}
                        {% for group_name, items in m.links|groupby('name') %}
                        <div class="link-group border border-secondary rounded bg-dark p-3">
                            <button class="btn btn-outline-warning w-100 fw-bold d-flex justify-content-between align-items-center" data-bs-toggle="collapse" data-bs-target="#col_movie_{{ loop.index }}" style="height: 60px;">
                                <span class="fs-4">
                                    {% if 'online' in group_name.lower() or 'watch' in group_name.lower() %}<i class="fas fa-play-circle"></i>
                                    {% elif 'telegram' in group_name.lower() %}<i class="fab fa-telegram"></i>
                                    {% else %}<i class="fas fa-download"></i>{% endif %}
                                    {{ group_name }}
                                </span>
                                <i class="fas fa-chevron-down fs-4"></i>
                            </button>
                            <div class="collapse mt-3" id="col_movie_{{ loop.index }}">
                                <div class="row g-3">
                                    {% for item in items %}
                                    <div class="col-md-6 col-lg-4">
                                        <a href="{{ item.url }}" onclick="checkAd(event, '{{ item.url }}')" class="btn btn-primary w-100 d-flex justify-content-between align-items-center p-3 shadow-sm fs-5">
                                            <span><i class="fas fa-link"></i> Click to Open</span>
                                            {% if item.quality %}<span class="badge bg-light text-dark px-3 py-2 fs-6">{{ item.quality }}</span>{% endif %}
                                        </a>
                                    </div>
                                    {% endfor %}
                                </div>
                            </div>
                        </div>
                        {% endfor %}
                    {% else %}
                        <div class="alert alert-secondary w-100 text-center fs-5">No links available yet.</div>
                    {% endif %}
                </div>
            {% else %}
                <h3 class="mb-4 fw-bold border-start border-warning border-4 ps-3">Seasons & Episodes</h3>
                
                <!-- Vertical Scroll for Seasons -->
                <div class="p-3 border border-secondary rounded mb-4 shadow-sm" style="background:#151b2b; max-height: 350px; overflow-y: auto; scrollbar-width: thin;">
                    <ul class="nav nav-pills flex-column gap-3" id="seasonTabs" role="tablist">
                        {% for s in m.seasons %}
                        <li class="nav-item" role="presentation">
                            <button class="nav-link w-100 text-start {% if loop.first %}active{% endif %} fw-bold rounded fs-5 p-3" data-bs-toggle="pill" data-bs-target="#season_{{ s.season }}" type="button" role="tab">
                                <i class="fas fa-folder-open me-3"></i> Season {{ "%02d"|format(s.season|int) }}
                            </button>
                        </li>
                        {% endfor %}
                    </ul>
                </div>

                <div class="tab-content" id="seasonTabsContent">
                    {% for s in m.seasons %}
                    <div class="tab-pane fade {% if loop.first %}show active{% endif %}" id="season_{{ s.season }}" role="tabpanel">
                        
                        <!-- Episodes Grid Desktop Optimized -->
                        <div class="row g-3">
                            {% for ep in s.episodes %}
                                <div class="col-12 col-xl-6">
                                    <div class="ep-box p-3">
                                        <!-- EPISODE POSTER INCLUDED HERE -->
                                        <button class="btn btn-outline-primary w-100 text-start fw-bold d-flex justify-content-between align-items-center p-3" data-bs-toggle="collapse" data-bs-target="#links_S{{s.season}}_E{{ep.episode}}>
                                            <div class="d-flex align-items-center gap-4">
                                                <!-- Thumb Image: Episode Poster fallback to main backdrop fallback to portrait -->
                                                <img src="{{ ep.poster or m.backdrop or m.poster }}" class="shadow-sm" style="width: 140px; height: 80px; object-fit: cover; border-radius: 6px; border: 1px solid #2d3748;" onerror="this.src='{{ m.backdrop or m.poster }}'">
                                                <div>
                                                    <span class="fs-5 text-white d-block mb-1"><i class="fas fa-tv me-2"></i> 
                                                        {% if ep.ep_title %}
                                                            {{ ep.ep_title }}
                                                        {% else %}
                                                            Season {{ "%02d"|format(s.season|int) }} - Episode {{ "%02d"|format(ep.episode|int) }}
                                                        {% endif %}
                                                    </span>
                                                    {% if ep.ep_title %}
                                                        <small class="text-primary opacity-75">S{{ "%02d"|format(s.season|int) }} E{{ "%02d"|format(ep.episode|int) }}</small>
                                                    {% endif %}
                                                </div>
                                            </div>
                                            <i class="fas fa-chevron-down fs-4 ms-2"></i>
                                        </button>
                                        
                                        <div id="links_S{{s.season}}_E{{ep.episode}}" class="collapse mt-3">
                                            <div class="d-flex flex-column gap-3">
                                                {% if ep.links %}
                                                    {% for group_name, items in ep.links|groupby('name') %}
                                                    <div class="border border-secondary rounded p-3" style="background: rgba(0,0,0,0.4);">
                                                        <button class="btn btn-outline-warning w-100 fw-bold d-flex justify-content-between align-items-center p-2 fs-5" data-bs-toggle="collapse" data-bs-target="#col_s{{s.season}}_e{{ep.episode}}_g{{loop.index}}">
                                                            <span>
                                                                {% if 'online' in group_name.lower() or 'watch' in group_name.lower() %}<i class="fas fa-play-circle"></i>
                                                                {% else %}<i class="fas fa-download"></i>{% endif %}
                                                                {{ group_name }}
                                                            </span>
                                                            <i class="fas fa-chevron-down"></i>
                                                        </button>
                                                        <div class="collapse mt-3" id="col_s{{s.season}}_e{{ep.episode}}_g{{loop.index}}">
                                                            <div class="row g-2">
                                                                {% for item in items %}
                                                                <div class="col-md-6">
                                                                    <a href="{{ item.url }}" onclick="checkAd(event, '{{ item.url }}')" class="btn btn-primary w-100 d-flex justify-content-between align-items-center p-2">
                                                                        <span><i class="fas fa-link"></i> Click to Open</span>
                                                                        {% if item.quality %}<span class="badge bg-light text-dark">{{ item.quality }}</span>{% endif %}
                                                                    </a>
                                                                </div>
                                                                {% endfor %}
                                                            </div>
                                                        </div>
                                                    </div>
                                                    {% endfor %}
                                                {% else %}
                                                    <span class="text-muted text-center w-100 d-block border border-secondary rounded p-3 fs-5">No links available</span>
                                                {% endif %}
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            {% endfor %}
                        </div>

                    </div>
                    {% endfor %}
                </div>
            {% endif %}
        </div>
    </div>
    """)
    rendered_html = render_frontend(html, page_name='detail', m=movie)
    set_cached_data(cache_key, host, rendered_html)
    return rendered_html

# ==========================================
# ADMIN AUTHENTICATION
# ==========================================

@app.route('/login', methods=['GET', 'POST'])
def admin_login():
    tenant = get_tenant()
    if request.method == 'POST':
        user = request.form.get('username')
        password = request.form.get('password')
        if user == tenant.get('admin_user') and password == tenant.get('admin_pass'):
            session['logged_in'] = True
            session['tenant_host'] = tenant.get('host')
            return redirect(url_for('admin_dashboard'))
        else:
            flash("ভুল ইউজারনেম বা পাসওয়ার্ড!")
            
    html = """
    <!DOCTYPE html><html data-bs-theme="dark"><head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Admin Login - {{ tenant.get('host') }}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    </head>
    <body style="background:#0b0f19;" class="d-flex justify-content-center align-items-center vh-100">
        <div class="card p-4 shadow-lg border-primary" style="background:#151b2b; width: 350px;">
            <h3 class="text-center text-white mb-4">Admin Login</h3>
            <p class="text-center text-warning small fw-bold">Domain: {{ tenant.get('host') }}</p>
            {% if get_flashed_messages() %}
                <div class="alert alert-danger p-2 text-center">{{ get_flashed_messages()[0] }}</div>
            {% endif %}
            <form method="POST">
                <input type="text" name="username" class="form-control mb-3 bg-dark text-white border-secondary" placeholder="Username" required>
                <input type="password" name="password" class="form-control mb-3 bg-dark text-white border-secondary" placeholder="Password" required>
                <button type="submit" class="btn btn-primary w-100 fw-bold">Login</button>
            </form>
        </div>
    </body></html>
    """
    return render_template_string(html, tenant=tenant)

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    session.pop('tenant_host', None)
    return redirect(url_for('home'))

# ==========================================
# ADMIN ROUTES (Backend)
# ==========================================

@app.route('/admin')
@login_required
def admin_dashboard():
    total_movies = movies_col.count_documents({"type": "Movie"})
    total_series = movies_col.count_documents({"type": {"$in": ["Series", "Drama"]}})
    total_views = sum([m.get('views', 0) for m in movies_col.find()])
    html = ADMIN_HTML.replace('<!-- CONTENT_BLOCK -->', """
    <h2 class="fw-bold border-start border-primary border-4 ps-2 mb-4">ড্যাশবোর্ড (Dashboard)</h2>
    <div class="row">
        <div class="col-md-4 mb-3">
            <div class="card p-4 text-center border-bottom border-primary border-4">
                <h2 class="text-primary fw-bold">{{ tm }}</h2>
                <h6 class="text-muted m-0 text-uppercase">Total Movies (Global)</h6>
            </div>
        </div>
        <div class="col-md-4 mb-3">
            <div class="card p-4 text-center border-bottom border-success border-4">
                <h2 class="text-success fw-bold">{{ ts }}</h2>
                <h6 class="text-muted m-0 text-uppercase">Total Series/Drama (Global)</h6>
            </div>
        </div>
        <div class="col-md-4 mb-3">
            <div class="card p-4 text-center border-bottom border-warning border-4">
                <h2 class="text-warning fw-bold">{{ tv }}</h2>
                <h6 class="text-muted m-0 text-uppercase">Total Views (Global)</h6>
            </div>
        </div>
    </div>
    """).replace('<!-- SCRIPTS_BLOCK -->', "")
    return render_admin(html, tm=total_movies, ts=total_series, tv=total_views)


# ==========================================
# VERCEL API FUNCTIONS FOR AUTO DOMAIN ADD/REMOVE
# ==========================================
def add_domain_to_vercel(domain):
    VERCEL_TOKEN = os.environ.get("VERCEL_TOKEN", "your_vercel_token_here")
    PROJECT_ID = os.environ.get("VERCEL_PROJECT_ID", "your_project_id_here")
    
    if VERCEL_TOKEN == "your_vercel_token_here" or not VERCEL_TOKEN:
        return False, "Vercel Token বা Project ID সেট করা নেই!"

    headers = {
        "Authorization": f"Bearer {VERCEL_TOKEN}",
        "Content-Type": "application/json"
    }
    url = f"https://api.vercel.com/v10/projects/{PROJECT_ID}/domains"
    try:
        res = requests.post(url, headers=headers, json={"name": domain})
        if res.status_code in [200, 201]: 
            return True, "API Success: ভার্সেলে ডোমেইন অটোমেটিক এড হয়েছে!"
        else: 
            return False, f"API Error: {res.json().get('error', {}).get('message', 'Unknown Error')}"
    except Exception as e:
        return False, str(e)

def remove_domain_from_vercel(domain):
    VERCEL_TOKEN = os.environ.get("VERCEL_TOKEN", "your_vercel_token_here")
    PROJECT_ID = os.environ.get("VERCEL_PROJECT_ID", "your_project_id_here")
    if VERCEL_TOKEN == "your_vercel_token_here" or not VERCEL_TOKEN: 
        return
    headers = {"Authorization": f"Bearer {VERCEL_TOKEN}"}
    url = f"https://api.vercel.com/v9/projects/{PROJECT_ID}/domains/{domain}"
    try: 
        requests.delete(url, headers=headers)
    except: 
        pass


# 🚀 NEW FEATURE: UNLIMITED CUSTOM DOMAINS MANAGEMENT (.com / .xyz) & DNS GENERATOR
@app.route('/admin/domains', methods=['GET', 'POST'])
@login_required
def manage_domains():
    tenant = get_tenant()
    if not tenant.get('is_main'):
        return "<h2 style='color:red;'>Access Denied. Only Main Admin can manage Domains.</h2>", 403
        
    dns_info = None # নতুন ডোমেন এড করলে DNS ইনফো দেখানোর জন্য
        
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            host = request.form.get('host').strip().lower()
            # Remove http:// or www. if typed accidentally
            host = host.replace("http://", "").replace("https://", "").replace("www.", "").strip('/')
            
            user = request.form.get('admin_user').strip()
            password = request.form.get('admin_pass').strip()
            price = request.form.get('price', 0)
            months = int(request.form.get('months', 1))
            expire_at = time.time() + (months * 30 * 24 * 3600) # Calculate exact lock date
            
            if domains_col.find_one({"host": host}):
                flash("Error: এই ডোমেনটি আগেই তৈরি করা আছে!")
            else:
                domains_col.insert_one({
                    "host": host,
                    "is_main": False,
                    "admin_user": user,
                    "admin_pass": password,
                    "price_paid": int(price),
                    "expire_at": expire_at,
                    "settings": tenant.get('settings', {}) # Copy initial settings from main site
                })
                
                # 🚀 Vercel API Call - Auto Add Domain
                api_success, api_msg = add_domain_to_vercel(host)
                
                # ডোমেন এড হওয়ার পর DNS রেকর্ড জেনারেট করা হচ্ছে (For Vercel)
                dns_info = {
                    "domain": host,
                    "a_record": "76.76.21.21", 
                    "cname": "cname.vercel-dns.com",
                    "api_status": api_msg,
                    "api_success": api_success
                }
                flash(f"ডোমেন {host} সফলভাবে ডাটাবেসে যুক্ত হয়েছে!")
                
        elif action == 'renew':
            tenant_id = request.form.get('tenant_id')
            months = int(request.form.get('months', 1))
            price = request.form.get('price', 0)
            t = domains_col.find_one({"_id": ObjectId(tenant_id)})
            if t:
                current_expire = t.get('expire_at', time.time())
                if current_expire < time.time():
                    current_expire = time.time() # Start from today if already expired
                new_expire = current_expire + (months * 30 * 24 * 3600)
                domains_col.update_one({"_id": ObjectId(tenant_id)}, {"$set": {"expire_at": new_expire}, "$inc": {"price_paid": int(price)}})
                flash("ডোমেনটির মেয়াদ সফলভাবে বাড়ানো হয়েছে!")
                return redirect(url_for('manage_domains'))
                
        elif action == 'delete':
            tenant_id = request.form.get('tenant_id')
            t = domains_col.find_one({"_id": ObjectId(tenant_id)})
            if t:
                # 🚀 Vercel API Call - Auto Remove Domain
                remove_domain_from_vercel(t['host'])
            
            domains_col.delete_one({"_id": ObjectId(tenant_id)})
            flash("ডোমেনটি সফলভাবে মুছে ফেলা হয়েছে!")
            return redirect(url_for('manage_domains'))
            
    domains_list = list(domains_col.find({"is_main": False}).sort('_id', -1))
    current_time = time.time()
    
    import datetime
    def format_time(ts):
        return datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M')

    html = ADMIN_HTML.replace('<!-- CONTENT_BLOCK -->', """
    <h2 class="fw-bold border-start border-primary border-4 ps-2 mb-4">কাস্টম ডোমেন ও DNS ম্যানেজমেন্ট</h2>
    
    {% if dns_info %}
    <!-- 🚀 ডোমেন এড করার পর DNS রেকর্ড শো করবে -->
    <div class="card p-4 mb-4 border-warning shadow" style="background:#1e2738;">
        <h4 class="text-warning fw-bold mb-3"><i class="fas fa-server"></i> ডোমেন কানেক্ট করার নিয়ম</h4>
        <p class="text-white"><b>{{ dns_info.domain }}</b> সাইটটি লাইভ করার জন্য ক্লায়েন্টকে তার ডোমেন প্যানেলে (Cloudflare/Namecheap) গিয়ে নিচের রেকর্ড দুটি বসাতে বলুন:</p>
        
        <div class="table-responsive">
            <table class="table table-bordered table-dark text-center align-middle">
                <thead><tr class="text-info"><th>Type</th><th>Name / Host</th><th>Value / Target</th></tr></thead>
                <tbody>
                    <tr>
                        <td><span class="badge bg-primary fs-6">A Record</span></td>
                        <td class="fw-bold">@</td>
                        <td class="text-success fw-bold fs-5">{{ dns_info.a_record }}</td>
                    </tr>
                    <tr>
                        <td><span class="badge bg-info fs-6">CNAME</span></td>
                        <td class="fw-bold">www</td>
                        <td class="text-warning fw-bold fs-5">{{ dns_info.cname }}</td>
                    </tr>
                </tbody>
            </table>
        </div>
        
        <!-- API STATUS ALERT -->
        {% if dns_info.api_success %}
        <div class="alert alert-success p-2 mt-2">
            <i class="fas fa-check-circle"></i> <b>অভিনন্দন:</b> {{ dns_info.api_status }} আপনাকে আর Vercel-এ ঢুকতে হবে না। ক্লায়েন্ট DNS বসালেই সাইট লাইভ!
        </div>
        {% else %}
        <div class="alert alert-danger p-2 mt-2">
            <i class="fas fa-exclamation-triangle"></i> <b>API Failed:</b> {{ dns_info.api_status }}<br>
            <i>(আপনাকে হয়তো ডোমেইনটি ম্যানুয়ালি Vercel Dashboard-এ গিয়ে Settings > Domains থেকে Add করতে হবে।)</i>
        </div>
        {% endif %}
    </div>
    {% endif %}

    <div class="card p-4 mb-4 shadow border-success" style="background:#151b2b;">
        <h4 class="text-success fw-bold mb-3"><i class="fas fa-plus"></i> নতুন ডোমেন এড করুন</h4>
        <form method="POST">
            <input type="hidden" name="action" value="add">
            <div class="row">
                <div class="col-md-3 mb-3"><label>Custom Domain (Ex: movies.com)</label><input type="text" name="host" class="form-control border-success" placeholder="example.com" required></div>
                <div class="col-md-3 mb-3"><label>Client Username</label><input type="text" name="admin_user" class="form-control" required></div>
                <div class="col-md-2 mb-3"><label>Client Password</label><input type="text" name="admin_pass" class="form-control" required></div>
                <div class="col-md-2 mb-3"><label>Price Paid (৳)</label><input type="number" name="price" class="form-control" value="0"></div>
                <div class="col-md-2 mb-3"><label>Duration (Months)</label><input type="number" name="months" class="form-control" value="1" min="1"></div>
            </div>
            <button type="submit" class="btn btn-success w-100 fw-bold fs-5">Generate DNS & Auto Add to Vercel</button>
        </form>
    </div>

    <div class="card p-4 shadow" style="background:#151b2b;">
        <h4 class="text-info fw-bold mb-3"><i class="fas fa-list"></i> অল ডোমেন লিস্ট</h4>
        <div class="table-responsive">
            <table class="table table-dark table-hover align-middle border-secondary">
                <thead>
                    <tr class="text-warning">
                        <th>Domain / URL</th>
                        <th>User / Pass</th>
                        <th>Total Paid</th>
                        <th>Expire Date</th>
                        <th>Status</th>
                        <th>Action</th>
                    </tr>
                </thead>
                <tbody>
                    {% for sub in domains_list %}
                    <tr>
                        <td class="fw-bold text-white">{{ sub.host }}</td>
                        <td>{{ sub.admin_user }} / {{ sub.admin_pass }}</td>
                        <td class="text-success">{{ sub.price_paid }} ৳</td>
                        <td>{{ format_time(sub.expire_at) }}</td>
                        <td>
                            {% if sub.expire_at < current_time %}
                                <span class="badge bg-danger fs-6">Locked</span>
                            {% else %}
                                <span class="badge bg-success fs-6">Active</span>
                            {% endif %}
                        </td>
                        <td>
                            <!-- Renew System -->
                            <form method="POST" class="d-inline border p-1 rounded border-secondary" style="background: rgba(255,255,255,0.05);">
                                <input type="hidden" name="action" value="renew">
                                <input type="hidden" name="tenant_id" value="{{ sub._id }}">
                                <input type="number" name="months" class="form-control form-control-sm d-inline" style="width:70px;" value="1" min="1" placeholder="Months">
                                <input type="number" name="price" class="form-control form-control-sm d-inline" style="width:80px;" value="0" placeholder="Price">
                                <button type="submit" class="btn btn-sm btn-primary fw-bold">Renew</button>
                            </form>
                            <!-- Delete System -->
                            <form method="POST" class="d-inline ms-2" onsubmit="return confirm('ডোমেনটি কি ডিলেট করতে চান? এটি Vercel থেকেও ডিলেট হয়ে যাবে!');">
                                <input type="hidden" name="action" value="delete">
                                <input type="hidden" name="tenant_id" value="{{ sub._id }}">
                                <button type="submit" class="btn btn-sm btn-outline-danger"><i class="fas fa-trash"></i></button>
                            </form>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
    """).replace('<!-- SCRIPTS_BLOCK -->', "")
    return render_admin(html, domains_list=domains_list, format_time=format_time, current_time=current_time, dns_info=dns_info)

@app.route('/admin/settings', methods=['GET', 'POST'])
@login_required
def admin_settings():
    tenant = get_tenant()
    active_types = movies_col.distinct("type")
    all_types = list(set(active_types + ["Movie", "Series", "Drama", "Anime"]))

    if request.method == 'POST':
        clear_cache()
        d_links = request.form.getlist('direct_links[]')
        d_links = [url for url in d_links if url.strip()]
        
        p_texts = request.form.getlist('promo_text[]')
        p_images = request.form.getlist('promo_image[]')
        p_urls = request.form.getlist('promo_url[]')
        promos = [{"text": t, "image": i, "url": u} for t, i, u in zip(p_texts, p_images, p_urls) if t and u]
        
        limits = {"Episode": request.form.get('limit_Episode', '12')}
        for t in all_types:
            limits[t] = request.form.get(f"limit_{t}", "12")
        
        new_settings = {
            "ad_status_banner": request.form.get('ad_status_banner'),
            "ad_status_direct": request.form.get('ad_status_direct'),
            "ad_banner_home_desktop": request.form.get('ad_banner_home_desktop'),
            "ad_banner_home_mobile": request.form.get('ad_banner_home_mobile'),
            "ad_banner_detail_desktop": request.form.get('ad_banner_detail_desktop'),
            "ad_banner_detail_mobile": request.form.get('ad_banner_detail_mobile'),
            "ad_banner_popular": request.form.get('ad_banner_popular'),
            "ad_header": request.form.get('ad_header'),
            "ad_middle": request.form.get('ad_middle'),
            "ad_footer": request.form.get('ad_footer'),
            "direct_links": d_links,
            "telegram_link": request.form.get('telegram_link'),
            "notice": request.form.get('notice'),
            "popup_notice": request.form.get('popup_notice'),
            "tmdb_api_key": request.form.get('tmdb_api_key'),
            "limits": limits,
            "promos": promos
        }
        
        new_user = request.form.get('admin_user')
        new_pass = request.form.get('admin_pass')
        
        # Save specific to this Domain
        domains_col.update_one({"_id": tenant['_id']}, {"$set": {
            "admin_user": new_user,
            "admin_pass": new_pass,
            "settings": new_settings
        }})
        flash("আপনার সাইটের সেটিংস এবং অ্যাডস সফলভাবে আপডেট হয়েছে!")
        return redirect(url_for('admin_settings'))
    
    s = tenant.get('settings', {})
        
    html = ADMIN_HTML.replace('<!-- CONTENT_BLOCK -->', """
    <h2 class="fw-bold border-start border-primary border-4 ps-2 mb-4">সেটিংস ও এডস প্যানেল (Domain: <span class="text-warning">{{ t_host }}</span>)</h2>
    <form method="POST" class="card p-4">
        
        <h5 class="text-danger border-bottom border-secondary pb-2"><i class="fas fa-layer-group"></i> Homepage Category Post Limits</h5>
        <div class="row mb-4 bg-dark p-3 rounded border border-secondary">
            <div class="col-md-3 mb-2">
                <label class="text-white fw-bold">Episodes Section</label>
                <input type="number" name="limit_Episode" class="form-control border-danger" value="{{ s.get('limits', {}).get('Episode', '12') }}" min="1">
            </div>
            {% for t in all_types %}
            <div class="col-md-3 mb-2">
                <label class="text-white">{{ t }} Section Limit</label>
                <input type="number" name="limit_{{ t }}" class="form-control" value="{{ s.get('limits', {}).get(t, '12') }}" min="1">
            </div>
            {% endfor %}
        </div>

        <h5 class="text-warning border-bottom border-secondary pb-2"><i class="fas fa-money-bill-wave"></i> Unlimited Promote & Income System</h5>
        <div class="row mb-4 bg-dark p-3 rounded border border-warning">
            <div class="col-12">
                <label class="mb-2 text-warning">এই প্রোমোগুলো হোমপেজের প্রতি ক্যাটাগরির নিচে শো করবে</label>
                <div id="promoContainer">
                    {% for p in s.get('promos', []) %}
                    <div class="input-group mb-2 border border-secondary p-1 bg-black rounded">
                        <input type="text" name="promo_text[]" class="form-control" value="{{ p.text }}" placeholder="Promo Text Title" required>
                        <input type="url" name="promo_image[]" class="form-control" value="{{ p.image }}" placeholder="Image/Screenshot URL" required>
                        <input type="url" name="promo_url[]" class="form-control" value="{{ p.url }}" placeholder="Destination Link" required>
                        <button type="button" class="btn btn-danger" onclick="this.parentElement.remove()"><i class="fas fa-trash"></i></button>
                    </div>
                    {% endfor %}
                </div>
                <button type="button" class="btn btn-outline-warning mt-2 fw-bold w-100" onclick="addPromo()"><i class="fas fa-plus"></i> Add New Promo</button>
            </div>
        </div>
        
        <h5 class="text-primary border-bottom border-secondary pb-2"><i class="fas fa-ad"></i> Global Ads (Header, Middle, Footer)</h5>
        <div class="row mb-4 bg-dark p-3 rounded border border-primary">
            <div class="col-md-12 mb-3">
                <label class="text-white"><i class="fas fa-arrow-up"></i> Header Ad (Show at Top)</label>
                <textarea name="ad_header" class="form-control" rows="3" placeholder="HTML Code for Top Ad">{{ s.get('ad_header', '') }}</textarea>
            </div>
            <div class="col-md-12 mb-3">
                <label class="text-white"><i class="fas fa-arrows-alt-v"></i> Middle Ad (Show in Center)</label>
                <textarea name="ad_middle" class="form-control" rows="3" placeholder="HTML Code for Middle Ad">{{ s.get('ad_middle', '') }}</textarea>
            </div>
            <div class="col-md-12 mb-3">
                <label class="text-white"><i class="fas fa-arrow-down"></i> Footer Ad (Show at Bottom)</label>
                <textarea name="ad_footer" class="form-control" rows="3" placeholder="HTML Code for Bottom Ad">{{ s.get('ad_footer', '') }}</textarea>
            </div>
        </div>

        <h5 class="text-info border-bottom border-secondary pb-2"><i class="fas fa-link"></i> Direct Ads (Auto Switch on Click)</h5>
        <div class="row mb-4 bg-dark p-3 rounded">
            <div class="col-md-12 mb-3">
                <label class="text-warning fw-bold">Direct Ads Status</label>
                <select name="ad_status_direct" class="form-select border-warning">
                    <option value="on" {% if s.get('ad_status_direct') == 'on' %}selected{% endif %}>ON (চালু)</option>
                    <option value="off" {% if s.get('ad_status_direct') == 'off' %}selected{% endif %}>OFF (বন্ধ)</option>
                </select>
            </div>
            <div class="col-12">
                <label class="mb-2 text-info">Add Unlimited Direct Links (প্রতি ক্লিকে অটো পরিবর্তন হবে)</label>
                <div id="directLinkContainer">
                    {% for d_link in s.get('direct_links', []) %}
                    <div class="input-group mb-2">
                        <span class="input-group-text bg-secondary text-white"><i class="fas fa-external-link-alt"></i></span>
                        <input type="url" name="direct_links[]" class="form-control" value="{{ d_link }}" placeholder="https://ad-network.com/..." required>
                        <button type="button" class="btn btn-danger" onclick="this.parentElement.remove()"><i class="fas fa-trash"></i></button>
                    </div>
                    {% endfor %}
                </div>
                <button type="button" class="btn btn-outline-info mt-2 btn-sm fw-bold" onclick="addDirectLink()"><i class="fas fa-plus"></i> Add Link</button>
            </div>
        </div>

        <h5 class="text-success border-bottom border-secondary pb-2"><i class="fas fa-image"></i> Banner Ads (HTML Code)</h5>
        <div class="row mb-4 bg-dark p-3 rounded">
            <div class="col-md-12 mb-3">
                <label class="text-warning fw-bold">Banner Ads Status</label>
                <select name="ad_status_banner" class="form-select border-warning">
                    <option value="on" {% if s.get('ad_status_banner') == 'on' %}selected{% endif %}>ON (চালু)</option>
                    <option value="off" {% if s.get('ad_status_banner') == 'off' %}selected{% endif %}>OFF (বন্ধ)</option>
                </select>
            </div>
            <div class="col-md-12 mb-3">
                <label class="text-warning"><i class="fas fa-star"></i> Popular Ad Banner (All Pages, Top Section)</label>
                <textarea name="ad_banner_popular" class="form-control border-warning" rows="3" placeholder="Paste popular banner code here">{{ s.get('ad_banner_popular', '') }}</textarea>
            </div>
            <div class="col-md-6 mb-3">
                <label class="text-white"><i class="fas fa-home"></i> Home Page (Desktop)</label>
                <textarea name="ad_banner_home_desktop" class="form-control" rows="3" placeholder="Paste desktop banner code here">{{ s.get('ad_banner_home_desktop', '') }}</textarea>
            </div>
            <div class="col-md-6 mb-3">
                <label class="text-white"><i class="fas fa-mobile-alt"></i> Home Page (Mobile)</label>
                <textarea name="ad_banner_home_mobile" class="form-control" rows="3" placeholder="Paste mobile banner code here">{{ s.get('ad_banner_home_mobile', '') }}</textarea>
            </div>
            <div class="col-md-6 mb-3">
                <label class="text-white"><i class="fas fa-film"></i> Detail Page (Desktop)</label>
                <textarea name="ad_banner_detail_desktop" class="form-control" rows="3" placeholder="Paste desktop banner code here">{{ s.get('ad_banner_detail_desktop', '') }}</textarea>
            </div>
            <div class="col-md-6 mb-3">
                <label class="text-white"><i class="fas fa-mobile-alt"></i> Detail Page (Mobile)</label>
                <textarea name="ad_banner_detail_mobile" class="form-control" rows="3" placeholder="Paste mobile banner code here">{{ s.get('ad_banner_detail_mobile', '') }}</textarea>
            </div>
        </div>

        <h5 class="text-warning border-bottom border-secondary pb-2"><i class="fas fa-shield-alt"></i> Security / API</h5>
        <div class="row mb-4">
            <div class="col-md-4 mb-2"><label>Admin Username</label><input type="text" name="admin_user" class="form-control" value="{{ admin_user }}" required></div>
            <div class="col-md-4 mb-2"><label>Admin Password</label><input type="text" name="admin_pass" class="form-control" value="{{ admin_pass }}" required></div>
            <div class="col-md-4 mb-2"><label>TMDB API Key V3</label><input type="text" name="tmdb_api_key" class="form-control" value="{{ s.get('tmdb_api_key', '') }}" placeholder="Required for TMDB Import"></div>
        </div>

        <h5 class="text-primary border-bottom border-secondary pb-2"><i class="fas fa-bullhorn"></i> Notice & Telegram</h5>
        <div class="row mb-4">
            <div class="col-md-12 mb-2"><label>Telegram Link</label><input type="text" name="telegram_link" class="form-control" value="{{ s.get('telegram_link', '') }}"></div>
            <div class="col-md-12 mb-2"><label>General Notice (Top bar)</label><input type="text" name="notice" class="form-control" value="{{ s.get('notice', '') }}"></div>
        </div>
        
        <button type="submit" class="btn btn-primary fw-bold px-5 fs-5 w-100">Save All Settings</button>
    </form>
    """).replace('<!-- SCRIPTS_BLOCK -->', """
    <script>
        function addDirectLink() {
            let div = document.createElement('div');
            div.className = "input-group mb-2";
            div.innerHTML = `
                <span class="input-group-text bg-secondary text-white"><i class="fas fa-external-link-alt"></i></span>
                <input type="url" name="direct_links[]" class="form-control" placeholder="https://ad-network.com/..." required>
                <button type="button" class="btn btn-danger" onclick="this.parentElement.remove()"><i class="fas fa-trash"></i></button>`;
            document.getElementById('directLinkContainer').appendChild(div);
        }
        function addPromo() {
            let div = document.createElement('div');
            div.className = "input-group mb-2 border border-secondary p-1 bg-black rounded";
            div.innerHTML = `
                <input type="text" name="promo_text[]" class="form-control" placeholder="Promo Text Title" required>
                <input type="url" name="promo_image[]" class="form-control" placeholder="Image/Screenshot URL" required>
                <input type="url" name="promo_url[]" class="form-control" placeholder="Destination Link" required>
                <button type="button" class="btn btn-danger" onclick="this.parentElement.remove()"><i class="fas fa-trash"></i></button>`;
            document.getElementById('promoContainer').appendChild(div);
        }
    </script>
    """)
    return render_admin(html, s=s, all_types=all_types, admin_user=tenant.get('admin_user'), admin_pass=tenant.get('admin_pass'), t_host=tenant.get('host'))

@app.route('/admin/options', methods=['GET', 'POST'])
@login_required
def admin_options():
    if request.method == 'POST':
        item_type = request.form.get('type')
        item_val = request.form.get('value')
        options_col.insert_one({"type": item_type, "value": item_val})
        flash(f"{item_val} যোগ করা হয়েছে!")
        return redirect(url_for('admin_options'))
    
    badges = list(options_col.find({"type": "badge"}))
    qualities = list(options_col.find({"type": "quality"}))
    langs = list(options_col.find({"type": "language"}))
    cats = list(options_col.find({"type": "category"}))
    link_names = list(options_col.find({"type": "link_name"}))
    
    html = ADMIN_HTML.replace('<!-- CONTENT_BLOCK -->', """
    <h2 class="fw-bold border-start border-primary border-4 ps-2 mb-4">ক্যাটাগরি, ব্যাজ, লিংক নাম ও কোয়ালিটি (Global)</h2>
    <div class="card p-4">
        <form method="POST" class="d-flex gap-2 mb-4 flex-wrap">
            <select name="type" class="form-select" style="width: auto;">
                <option value="category">Category (Action..)</option>
                <option value="badge">Badge (CAM, HD..)</option>
                <option value="quality">Quality (1080p..)</option>
                <option value="language">Language (Hindi..)</option>
                <option value="link_name">Link Name (Download, Watch..)</option>
            </select>
            <input type="text" name="value" class="form-control flex-grow-1" placeholder="নাম লিখুন..." required>
            <button type="submit" class="btn btn-success fw-bold px-4">Add New</button>
        </form>
        
        <div class="row">
            <div class="col-md-3">
                <h5 class="text-info border-bottom pb-2">Categories</h5>
                <ul class="list-group list-group-flush bg-transparent">
                    {% for c in cats %}<li class="list-group-item bg-transparent text-white d-flex justify-content-between align-items-center border-secondary">{{ c.value }} <a href="/admin/del_opt/{{c._id}}" class="text-danger"><i class="fas fa-trash"></i></a></li>{% endfor %}
                </ul>
            </div>
            <div class="col-md-3">
                <h5 class="text-warning border-bottom pb-2">Badges</h5>
                <ul class="list-group list-group-flush">
                    {% for b in badges %}<li class="list-group-item bg-transparent text-white d-flex justify-content-between align-items-center border-secondary">{{ b.value }} <a href="/admin/del_opt/{{b._id}}" class="text-danger"><i class="fas fa-trash"></i></a></li>{% endfor %}
                </ul>
            </div>
            <div class="col-md-3">
                <h5 class="text-primary border-bottom pb-2">Qualities</h5>
                <ul class="list-group list-group-flush">
                    {% for q in qualities %}<li class="list-group-item bg-transparent text-white d-flex justify-content-between align-items-center border-secondary">{{ q.value }} <a href="/admin/del_opt/{{q._id}}" class="text-danger"><i class="fas fa-trash"></i></a></li>{% endfor %}
                </ul>
            </div>
            <div class="col-md-3">
                <h5 class="text-success border-bottom pb-2">Languages</h5>
                <ul class="list-group list-group-flush">
                    {% for l in langs %}<li class="list-group-item bg-transparent text-white d-flex justify-content-between align-items-center border-secondary">{{ l.value }} <a href="/admin/del_opt/{{l._id}}" class="text-danger"><i class="fas fa-trash"></i></a></li>{% endfor %}
                </ul>
            </div>
            
            <div class="col-12 mt-4">
                <h5 class="text-secondary border-bottom pb-2">Pre-added Link Names (For Download Buttons)</h5>
                <div class="d-flex flex-wrap gap-2">
                    {% for lnk in link_names %}
                        <span class="badge bg-secondary p-2 fs-6">{{ lnk.value }} <a href="/admin/del_opt/{{lnk._id}}" class="text-danger ms-2"><i class="fas fa-times"></i></a></span>
                    {% endfor %}
                </div>
            </div>
        </div>
    </div>
    """).replace('<!-- SCRIPTS_BLOCK -->', "")
    return render_admin(html, badges=badges, qualities=qualities, langs=langs, cats=cats, link_names=link_names)

@app.route('/admin/del_opt/<id>')
@login_required
def del_opt(id):
    options_col.delete_one({"_id": ObjectId(id)})
    return redirect(url_for('admin_options'))

@app.route('/admin/tmdb_search')
@login_required
def tmdb_search():
    query = request.args.get('q')
    tenant = get_tenant()
    
    # Check if Domain has API Key, else fallback to Main Admin Key
    api_key = tenant.get('settings', {}).get('tmdb_api_key')
    if not api_key:
        main_tenant = domains_col.find_one({"is_main": True})
        if main_tenant:
            api_key = main_tenant.get('settings', {}).get('tmdb_api_key')

    if not api_key or not query:
        return jsonify([])
    
    url = f"https://api.themoviedb.org/3/search/multi?api_key={api_key}&query={query}&language=en-US&page=1"
    try:
        res = requests.get(url).json()
        results = []
        for item in res.get('results', []):
            if item.get('media_type') in ['movie', 'tv']:
                title = item.get('title') if item.get('media_type') == 'movie' else item.get('name')
                date = item.get('release_date') if item.get('media_type') == 'movie' else item.get('first_air_date')
                poster = f"https://image.tmdb.org/t/p/w92{item.get('poster_path')}" if item.get('poster_path') else "https://via.placeholder.com/92x138?text=No+Image"
                results.append({
                    'id': item.get('id'),
                    'title': title,
                    'type': item.get('media_type'),
                    'date': date,
                    'poster': poster
                })
        return jsonify(results)
    except:
        return jsonify([])

@app.route('/admin/add_movie', methods=['GET', 'POST'])
@login_required
def add_movie():
    tenant = get_tenant()
    active_types = movies_col.distinct("type")
    all_types = list(set(active_types + ["Movie", "Series", "Drama", "Anime"]))
    
    if request.method == 'POST':
        clear_cache() # Clear global cache so it syncs across all domains
        action = request.form.get('action')
        
        if action == 'fetch_tmdb':
            tmdb_input = request.form.get('tmdb_id').strip()
            m_type = request.form.get('fetch_type')
            
            api_key = tenant.get('settings', {}).get('tmdb_api_key')
            if not api_key:
                main_tenant = domains_col.find_one({"is_main": True})
                if main_tenant:
                    api_key = main_tenant.get('settings', {}).get('tmdb_api_key')

            if not api_key:
                flash("Error: TMDB API Key সেটিংসে দেওয়া নেই!")
                return redirect(url_for('add_movie'))
            
            imdb_match = re.search(r'(tt\d+)', tmdb_input)
            tmdb_match = re.search(r'themoviedb\.org/(movie|tv)/(\d+)', tmdb_input)
            
            if imdb_match:
                imdb_id = imdb_match.group(1)
                find_url = f"https://api.themoviedb.org/3/find/{imdb_id}?api_key={api_key}&external_source=imdb_id"
                try:
                    res = requests.get(find_url).json()
                    if res.get('movie_results'):
                        tmdb_input = str(res['movie_results'][0]['id'])
                        m_type = 'movie'
                    elif res.get('tv_results'):
                        tmdb_input = str(res['tv_results'][0]['id'])
                        m_type = 'tv'
                    else:
                        flash("Error: IMDB ID দিয়ে TMDB তে ডাটা পাওয়া যায়নি!")
                        return redirect(url_for('add_movie'))
                except Exception as e:
                    flash(f"Error checking IMDB: {str(e)}")
                    return redirect(url_for('add_movie'))
            elif tmdb_match:
                m_type = tmdb_match.group(1)
                tmdb_input = tmdb_match.group(2)
            
            url = f"https://api.themoviedb.org/3/{m_type}/{tmdb_input}?api_key={api_key}&language=en-US"
            try:
                res = requests.get(url).json()
                if 'id' not in res:
                    flash("Error: TMDB ID সঠিক নয় বা ডাটা পাওয়া যায়নি!")
                    return redirect(url_for('add_movie'))
                
                title = res.get('title') if m_type == 'movie' else res.get('name')
                date = res.get('release_date') if m_type == 'movie' else res.get('first_air_date')
                
                poster = f"https://image.tmdb.org/t/p/w500{res.get('poster_path')}" if res.get('poster_path') else ""
                backdrop = f"https://image.tmdb.org/t/p/w780{res.get('backdrop_path')}" if res.get('backdrop_path') else poster
                
                desc = res.get('overview', '')
                
                genres = [g['name'] for g in res.get('genres', [])]
                for g in genres:
                    if not options_col.find_one({"type": "category", "value": g}):
                        options_col.insert_one({"type": "category", "value": g})
                
                new_doc = {
                    "title": title, "type": "Movie" if m_type == 'movie' else "Series",
                    "poster": poster, "backdrop": backdrop, "description": desc, "date": date,
                    "badge": "", "quality": "", "language": "English",
                    "categories": genres, "views": 0,
                    "links": []
                }
                
                if m_type == 'tv':
                    seasons = []
                    for s in res.get('seasons', []):
                        s_num = s.get('season_number')
                        if s_num > 0:
                            episodes = []
                            try:
                                s_res = requests.get(f"https://api.themoviedb.org/3/tv/{tmdb_input}/season/{s_num}?api_key={api_key}").json()
                                for e_data in s_res.get('episodes', []):
                                    e_num = e_data.get('episode_number')
                                    e_still = e_data.get('still_path')
                                    e_title = e_data.get('name', '')
                                    ep_poster = f"https://image.tmdb.org/t/p/w500{e_still}" if e_still else ""
                                    episodes.append({"episode": e_num, "ep_title": e_title, "poster": ep_poster, "links": []})
                            except:
                                episodes = [{"episode": e, "ep_title": "", "poster": "", "links": []} for e in range(1, s.get('episode_count') + 1)]
                                
                            seasons.append({"season": s_num, "episodes": episodes})
                    new_doc['seasons'] = seasons
                
                inserted_id = movies_col.insert_one(new_doc).inserted_id
                flash(f"TMDB থেকে '{title}' ইমপোর্ট হয়েছে! এখন লিংক বসান।")
                return redirect(f"/admin/edit_movie/{inserted_id}")
            except Exception as e:
                flash(f"Error connecting to TMDB: {str(e)}")
                return redirect(url_for('add_movie'))

        elif action == 'manual_add':
            title = request.form.get('title')
            m_type = request.form.get('type')
            
            link_names = request.form.getlist('link_name[]')
            link_quals = request.form.getlist('link_quality[]')
            link_urls = request.form.getlist('link_url[]')
            links = [{"name": n, "quality": q, "url": u} for n, q, u in zip(link_names, link_quals, link_urls) if n and u]
            
            poster = request.form.get('poster')
            backdrop = request.form.get('backdrop', poster)
            
            new_doc = {
                "title": title, "type": m_type, "poster": poster, "backdrop": backdrop,
                "badge": request.form.get('badge'), "quality": request.form.get('quality'),
                "language": request.form.get('language'), "description": request.form.get('description'),
                "categories": request.form.getlist('categories'), "views": 0,
                "links": links
            }
            
            if m_type not in ['Movie']:
                new_doc['seasons'] = [{"season": 1, "episodes": [{"episode": 1, "ep_title": "", "poster": "", "links": links}]}]
                new_doc['links'] = []
                
            movies_col.insert_one(new_doc)
            flash("ম্যানুয়ালি ডাটা যোগ করা হয়েছে!")
            return redirect(url_for('add_movie'))

    badges = list(options_col.find({"type": "badge"}))
    qualities = list(options_col.find({"type": "quality"}))
    langs = list(options_col.find({"type": "language"}))
    cats = list(options_col.find({"type": "category"}))
    link_names = list(options_col.find({"type": "link_name"}))

    html = ADMIN_HTML.replace('<!-- CONTENT_BLOCK -->', """
    <h2 class="fw-bold border-start border-primary border-4 ps-2 mb-4">মুভি / সিরিজ / ড্রামা এড (Global Network)</h2>
    <div class="alert alert-secondary bg-dark border-info text-info"><i class="fas fa-info-circle"></i> আপনি এখান থেকে মুভি এড করলে তা আপনার সমস্ত ক্লায়েন্টের ডোমেনে অটোমেটিক এড হয়ে যাবে।</div>

    <div class="card p-4 mb-4 border-success shadow" style="background:#151b2b;">
        <h4 class="text-success fw-bold mb-3"><i class="fas fa-search"></i> লাইভ TMDB সার্চ ও ইম্পোর্ট</h4>
        <div class="position-relative">
            <input type="text" id="liveSearchInput" class="form-control form-control-lg bg-dark text-white border-success" placeholder="মুভি বা সিরিজের নাম লিখুন...">
            <div id="liveSearchResults" class="list-group position-absolute w-100 shadow-lg" style="z-index: 1000; max-height: 400px; overflow-y: auto; display: none;">
            </div>
        </div>
        <form id="hiddenImportForm" method="POST" style="display:none;">
            <input type="hidden" name="action" value="fetch_tmdb">
            <input type="hidden" name="tmdb_id" id="hidden_tmdb_id">
            <input type="hidden" name="fetch_type" id="hidden_fetch_type">
        </form>
    </div>

    <div class="card p-4 mb-4 border-info shadow">
        <h4 class="text-info fw-bold mb-3"><i class="fas fa-hashtag"></i> TMDB বা IMDB লিংক দিয়ে ইম্পোর্ট</h4>
        <form method="POST" class="row align-items-end">
            <input type="hidden" name="action" value="fetch_tmdb">
            <div class="col-md-5 mb-2">
                <label>TMDB ID / TMDB URL / IMDB URL</label>
                <input type="text" name="tmdb_id" class="form-control" required placeholder="Paste full link or ID here">
            </div>
            <div class="col-md-4 mb-2">
                <label>Type (শুধু ID দিলে সিলেক্ট করুন)</label>
                <select name="fetch_type" class="form-select">
                    <option value="movie">Movie</option>
                    <option value="tv">TV Series / Drama</option>
                </select>
            </div>
            <div class="col-md-3 mb-2">
                <button type="submit" class="btn btn-info w-100 fw-bold text-dark"><i class="fas fa-cloud-download-alt"></i> Fetch Data</button>
            </div>
        </form>
    </div>

    <div class="card p-4 shadow">
        <h4 class="text-warning fw-bold mb-3"><i class="fas fa-edit"></i> Manual Publish</h4>
        <form method="POST">
            <input type="hidden" name="action" value="manual_add">
            <div class="row">
                <div class="col-md-6 mb-3"><label>Title</label><input type="text" name="title" class="form-control" required></div>
                <div class="col-md-3 mb-3">
                    <label>Type (ডাইনামিক)</label>
                    <select name="type" class="form-select">
                        {% for t in all_types %}
                            <option value="{{ t }}">{{ t }}</option>
                        {% endfor %}
                    </select>
                </div>
                <div class="col-md-3 mb-3"><label>Badge</label><select name="badge" class="form-select"><option value="">No Badge</option>{% for b in badges %}<option value="{{b.value}}">{{b.value}}</option>{% endfor %}</select></div>
                
                <div class="col-md-6 mb-3"><label>Poster URL (Portrait)</label><input type="url" name="poster" class="form-control" required></div>
                <div class="col-md-6 mb-3"><label>Backdrop URL (Landscape)</label><input type="url" name="backdrop" class="form-control" placeholder="Optional (Fallback to Poster)"></div>
                
                <div class="col-md-6 mb-3"><label>Quality</label><select name="quality" class="form-select"><option value="">Select..</option>{% for q in qualities %}<option value="{{q.value}}">{{q.value}}</option>{% endfor %}</select></div>
                <div class="col-md-6 mb-3"><label>Language</label><select name="language" class="form-select"><option value="">Select..</option>{% for l in langs %}<option value="{{l.value}}">{{l.value}}</option>{% endfor %}</select></div>
                
                <div class="col-12 mb-3">
                    <label>Categories</label><br>
                    {% for c in cats %}
                        <div class="form-check form-check-inline">
                            <input class="form-check-input" type="checkbox" name="categories" value="{{ c.value }}">
                            <label class="form-check-label">{{ c.value }}</label>
                        </div>
                    {% endfor %}
                </div>
                <div class="col-12 mb-3"><label>Description</label><textarea name="description" class="form-control" rows="3"></textarea></div>
            </div>
            
            <h5 class="mt-3 border-bottom border-secondary pb-2">Download Links (Unlimited)</h5>
            <div id="linkContainer">
                <div class="input-group mb-2 mt-2">
                    <select name="link_name[]" class="form-select" required>
                        <option value="">Select Name...</option>
                        {% for lnk in link_names %}<option value="{{ lnk.value }}">{{ lnk.value }}</option>{% endfor %}
                    </select>
                    <select name="link_quality[]" class="form-select">
                        <option value="">Quality...</option>
                        {% for q in qualities %}<option value="{{ q.value }}">{{ q.value }}</option>{% endfor %}
                    </select>
                    <input type="url" name="link_url[]" class="form-control" placeholder="URL Link">
                    <button type="button" class="btn btn-success" onclick="addLinkField('linkContainer', 'link_name[]', 'link_quality[]', 'link_url[]')"><i class="fas fa-plus"></i></button>
                </div>
            </div>
            <button type="submit" class="btn btn-primary w-100 mt-4 fw-bold fs-5">Publish Manual Post</button>
        </form>
    </div>
    """).replace('<!-- SCRIPTS_BLOCK -->', """
    <script>
        const linkNameOpts = `<option value="">Select Name...</option>{% for lnk in link_names %}<option value="{{ lnk.value }}">{{ lnk.value }}</option>{% endfor %}`;
        const qualOpts = `<option value="">Quality...</option>{% for q in qualities %}<option value="{{ q.value }}">{{ q.value }}</option>{% endfor %}`;

        function addLinkField(containerId, nameAttr, qualAttr, urlAttr) {
            let div = document.createElement('div');
            div.className = "input-group mb-2 mt-2";
            div.innerHTML = `
                <select name="${nameAttr}" class="form-select" required>${linkNameOpts}</select>
                <select name="${qualAttr}" class="form-select">${qualOpts}</select>
                <input type="url" name="${urlAttr}" class="form-control" placeholder="URL" required>
                <button type="button" class="btn btn-danger" onclick="this.parentElement.remove()"><i class="fas fa-times"></i></button>`;
            document.getElementById(containerId).appendChild(div);
        }

        const searchInput = document.getElementById('liveSearchInput');
        const searchResults = document.getElementById('liveSearchResults');
        
        let timeout = null;
        searchInput.addEventListener('input', function() {
            clearTimeout(timeout);
            const query = this.value;
            if(query.length < 2) {
                searchResults.style.display = 'none';
                return;
            }
            timeout = setTimeout(() => {
                fetch(`/admin/tmdb_search?q=${query}`)
                .then(res => res.json())
                .then(data => {
                    searchResults.innerHTML = '';
                    if(data.length > 0) {
                        data.forEach(item => {
                            const btn = document.createElement('button');
                            btn.className = "list-group-item list-group-item-action d-flex align-items-center bg-dark text-white border-secondary";
                            btn.innerHTML = `
                                <img src="${item.poster}" alt="poster" width="40" class="me-3 rounded">
                                <div>
                                    <h6 class="mb-0 fw-bold">${item.title} <span class="badge bg-secondary ms-2">${item.type.toUpperCase()}</span></h6>
                                    <small class="text-muted">${item.date || 'N/A'}</small>
                                </div>
                                <span class="ms-auto btn btn-sm btn-success fw-bold">Import</span>
                            `;
                            btn.onclick = () => {
                                document.getElementById('hidden_tmdb_id').value = item.id;
                                document.getElementById('hidden_fetch_type').value = item.type;
                                document.getElementById('hiddenImportForm').submit();
                            };
                            searchResults.appendChild(btn);
                        });
                        searchResults.style.display = 'block';
                    } else {
                        searchResults.innerHTML = '<div class="list-group-item bg-dark text-white border-secondary">কোনো রেজাল্ট পাওয়া যায়নি! API Key চেক করুন।</div>';
                        searchResults.style.display = 'block';
                    }
                });
            }, 500);
        });
        
        document.addEventListener('click', function(e) {
            if(e.target !== searchInput && !searchResults.contains(e.target)) {
                searchResults.style.display = 'none';
            }
        });
    </script>
    """)
    return render_admin(html, badges=badges, qualities=qualities, langs=langs, cats=cats, link_names=link_names, all_types=all_types)

@app.route('/admin/edit_movie/<id>', methods=['GET', 'POST'])
@login_required
def edit_movie(id):
    movie = movies_col.find_one({"_id": ObjectId(id)})
    
    if request.method == 'POST':
        clear_cache()
        update_data = {
            "title": request.form.get('title'),
            "poster": request.form.get('poster'),
            "backdrop": request.form.get('backdrop'),
            "badge": request.form.get('badge'),
            "quality": request.form.get('quality'),
            "language": request.form.get('language'),
            "description": request.form.get('description'),
            "categories": request.form.getlist('categories')
        }
        
        if movie['type'] == 'Movie':
            l_names = request.form.getlist('link_name[]')
            l_quals = request.form.getlist('link_quality[]')
            l_urls = request.form.getlist('link_url[]')
            update_data['links'] = [{"name": n, "quality": q, "url": u} for n, q, u in zip(l_names, l_quals, l_urls) if n and u]
        else:
            seasons = movie.get('seasons', [])
            for s in seasons:
                for ep in s['episodes']:
                    ep['ep_title'] = request.form.get(f"ep_title_S{s['season']}_E{ep['episode']}", "")
                    ep['poster'] = request.form.get(f"ep_poster_S{s['season']}_E{ep['episode']}", "")
                    
                    l_names = request.form.getlist(f"link_name_S{s['season']}_E{ep['episode']}[]")
                    l_quals = request.form.getlist(f"link_quality_S{s['season']}_E{ep['episode']}[]")
                    l_urls = request.form.getlist(f"link_url_S{s['season']}_E{ep['episode']}[]")
                    ep['links'] = [{"name": n, "quality": q, "url": u} for n, q, u in zip(l_names, l_quals, l_urls) if n and u]
            update_data['seasons'] = seasons
            
        movies_col.update_one({"_id": ObjectId(id)}, {"$set": update_data})
        flash("আপডেট সফলভাবে সেভ হয়েছে!")
        return redirect(f"/admin/edit_movie/{id}")

    badges = list(options_col.find({"type": "badge"}))
    qualities = list(options_col.find({"type": "quality"}))
    langs = list(options_col.find({"type": "language"}))
    cats = list(options_col.find({"type": "category"}))
    link_names = list(options_col.find({"type": "link_name"}))

    html = ADMIN_HTML.replace('<!-- CONTENT_BLOCK -->', """
    <h2 class="fw-bold border-start border-warning border-4 ps-2 mb-4">Edit: <span class="text-primary">{{ m.title }}</span></h2>
    
    <div class="card p-4">
        <form method="POST">
            <div class="row">
                <div class="col-md-12 mb-3"><label>Title</label><input type="text" name="title" class="form-control" value="{{ m.title }}"></div>
                <div class="col-md-6 mb-3"><label>Poster URL (Portrait)</label><input type="text" name="poster" class="form-control" value="{{ m.poster }}"></div>
                <div class="col-md-6 mb-3"><label>Backdrop URL (Landscape)</label><input type="text" name="backdrop" class="form-control" value="{{ m.backdrop | default(m.poster) }}"></div>
                
                <div class="col-4 mb-3"><label>Badge</label><select name="badge" class="form-select"><option value="">No Badge</option>{% for b in badges %}<option value="{{b.value}}" {% if m.badge==b.value %}selected{% endif %}>{{b.value}}</option>{% endfor %}</select></div>
                <div class="col-4 mb-3"><label>Quality</label><select name="quality" class="form-select"><option value="">Select..</option>{% for q in qualities %}<option value="{{q.value}}" {% if m.quality==q.value %}selected{% endif %}>{{q.value}}</option>{% endfor %}</select></div>
                <div class="col-4 mb-3"><label>Language</label><select name="language" class="form-select"><option value="">Select..</option>{% for l in langs %}<option value="{{l.value}}" {% if m.language==l.value %}selected{% endif %}>{{l.value}}</option>{% endfor %}</select></div>
                
                <div class="col-12 mb-3">
                    <label>Categories</label><br>
                    {% for c in cats %}
                        <div class="form-check form-check-inline">
                            <input class="form-check-input" type="checkbox" name="categories" value="{{ c.value }}" {% if m.categories and c.value in m.categories %}checked{% endif %}>
                            <label class="form-check-label">{{ c.value }}</label>
                        </div>
                    {% endfor %}
                </div>
                <div class="col-12 mb-3"><label>Description</label><textarea name="description" class="form-control" rows="4">{{ m.description }}</textarea></div>
            </div>
            
            <hr class="border-secondary my-4">
            
            {% if m.type == 'Movie' %}
                <h4 class="mb-3 text-info fw-bold">Download Links</h4>
                <div id="movieLinks">
                    {% for link in m.links %}
                    <div class="input-group mb-2">
                        <select name="link_name[]" class="form-select" required>
                            <option value="">Select Name...</option>
                            {% for lnk in link_names %}<option value="{{lnk.value}}" {% if link.name == lnk.value %}selected{% endif %}>{{lnk.value}}</option>{% endfor %}
                        </select>
                        <select name="link_quality[]" class="form-select">
                            <option value="">Quality...</option>
                            {% for q in qualities %}<option value="{{q.value}}" {% if link.quality == q.value %}selected{% endif %}>{{q.value}}</option>{% endfor %}
                        </select>
                        <input type="url" name="link_url[]" class="form-control" value="{{ link.url }}" required>
                        <button type="button" class="btn btn-danger" onclick="this.parentElement.remove()"><i class="fas fa-times"></i></button>
                    </div>
                    {% endfor %}
                </div>
                <button type="button" class="btn btn-success btn-sm mb-3 mt-2" onclick="addLinkField('movieLinks', 'link_name[]', 'link_quality[]', 'link_url[]')"><i class="fas fa-plus"></i> Add Link</button>
            {% else %}
                <h4 class="mb-3 text-info fw-bold">Seasons & Episodes Links</h4>
                <div class="accordion text-dark" id="adminSeasons">
                    {% for s in m.seasons %}
                    <div class="accordion-item mb-2 border-0 bg-transparent">
                        <h2 class="accordion-header">
                            <button class="accordion-button collapsed bg-dark text-white border border-secondary" type="button" data-bs-toggle="collapse" data-bs-target="#col_S{{ s.season }}">
                                Season {{ "%02d"|format(s.season|int) }}
                            </button>
                        </h2>
                        <div id="col_S{{ s.season }}" class="accordion-collapse collapse" data-bs-parent="#adminSeasons">
                            <div class="accordion-body bg-black text-white rounded border border-secondary mt-1">
                                {% for ep in s.episodes %}
                                    <div class="mb-3 p-3 border border-secondary rounded" style="background:#151b2b;">
                                        <h5 class="text-warning mb-3">Episode {{ "%02d"|format(ep.episode|int) }}</h5>
                                        
                                        <div class="row">
                                            <div class="col-md-6 mb-2">
                                                <input type="text" name="ep_title_S{{ s.season }}_E{{ ep.episode }}" class="form-control form-control-sm" value="{{ ep.ep_title | default('') }}" placeholder="Episode Name / Title (Optional)">
                                            </div>
                                            <div class="col-md-6 mb-2">
                                                <input type="text" name="ep_poster_S{{ s.season }}_E{{ ep.episode }}" class="form-control form-control-sm" value="{{ ep.poster | default('') }}" placeholder="Episode Thumbnail URL (Optional)">
                                            </div>
                                        </div>
                                        
                                        <div id="links_S{{ s.season }}_E{{ ep.episode }}">
                                            {% for link in ep.links %}
                                            <div class="input-group mb-2 mt-2">
                                                <select name="link_name_S{{ s.season }}_E{{ ep.episode }}[]" class="form-select" required>
                                                    <option value="">Select Name...</option>
                                                    {% for lnk in link_names %}<option value="{{lnk.value}}" {% if link.name == lnk.value %}selected{% endif %}>{{lnk.value}}</option>{% endfor %}
                                                </select>
                                                <select name="link_quality_S{{ s.season }}_E{{ ep.episode }}[]" class="form-select">
                                                    <option value="">Quality...</option>
                                                    {% for q in qualities %}<option value="{{q.value}}" {% if link.quality == q.value %}selected{% endif %}>{{q.value}}</option>{% endfor %}
                                                </select>
                                                <input type="url" name="link_url_S{{ s.season }}_E{{ ep.episode }}[]" class="form-control" value="{{ link.url }}" required>
                                                <button type="button" class="btn btn-danger" onclick="this.parentElement.remove()"><i class="fas fa-times"></i></button>
                                            </div>
                                            {% endfor %}
                                        </div>
                                        <button type="button" class="btn btn-outline-success btn-sm mt-2" onclick="addLinkField('links_S{{ s.season }}_E{{ ep.episode }}', 'link_name_S{{ s.season }}_E{{ ep.episode }}[]', 'link_quality_S{{ s.season }}_E{{ ep.episode }}[]', 'link_url_S{{ s.season }}_E{{ ep.episode }}[]')"><i class="fas fa-plus"></i> Add Link</button>
                                    </div>
                                {% endfor %}
                            </div>
                        </div>
                    </div>
                    {% endfor %}
                </div>
            {% endif %}
            
            <button type="submit" class="btn btn-primary w-100 fw-bold fs-5 mt-4">Save All Changes</button>
        </form>
    </div>
    """).replace('<!-- SCRIPTS_BLOCK -->', """
    <script>
        const linkNameOpts = `<option value="">Select Name...</option>{% for lnk in link_names %}<option value="{{ lnk.value }}">{{ lnk.value }}</option>{% endfor %}`;
        const qualOpts = `<option value="">Quality...</option>{% for q in qualities %}<option value="{{ q.value }}">{{ q.value }}</option>{% endfor %}`;

        function addLinkField(containerId, nameAttr, qualAttr, urlAttr) {
            let div = document.createElement('div');
            div.className = "input-group mb-2 mt-2";
            div.innerHTML = `
                <select name="${nameAttr}" class="form-select" required>${linkNameOpts}</select>
                <select name="${qualAttr}" class="form-select">${qualOpts}</select>
                <input type="url" name="${urlAttr}" class="form-control" placeholder="URL" required>
                <button type="button" class="btn btn-danger" onclick="this.parentElement.remove()"><i class="fas fa-times"></i></button>`;
            document.getElementById(containerId).appendChild(div);
        }
    </script>
    """)
    return render_admin(html, m=movie, badges=badges, qualities=qualities, langs=langs, cats=cats, link_names=link_names)

@app.route('/admin/all_movies')
@login_required
def all_movies():
    movies = list(movies_col.find().sort('_id', -1))
    html = ADMIN_HTML.replace('<!-- CONTENT_BLOCK -->', """
    <h2 class="fw-bold border-start border-primary border-4 ps-2 mb-4">লিস্ট ও ডিলেট ম্যানেজমেন্ট (Global)</h2>
    <div class="card p-4 shadow">
        <div class="d-flex flex-wrap justify-content-between mb-3 gap-2">
            <button class="btn btn-danger fw-bold" onclick="deleteSelected()"><i class="fas fa-trash"></i> Delete Selected</button>
            <input type="text" id="searchInput" class="form-control" style="max-width:300px;" placeholder="Search by name..." onkeyup="filterTable()">
        </div>
        <div class="table-responsive">
            <table class="table table-dark table-hover border-secondary align-middle" id="movieTable">
                <thead>
                    <tr class="text-info">
                        <th><input type="checkbox" class="form-check-input" onclick="toggleAll(this)"> All</th>
                        <th>Poster</th>
                        <th>Name</th>
                        <th>Type</th>
                        <th>Views</th>
                        <th>Action</th>
                    </tr>
                </thead>
                <tbody>
                    {% for m in movies %}
                    <tr>
                        <td><input type="checkbox" class="form-check-input movie-checkbox" value="{{ m._id }}"></td>
                        <td><img src="{{ m.poster }}" width="50" height="70" class="rounded" style="object-fit:cover;"></td>
                        <td class="fw-bold">{{ m.title }}</td>
                        <td><span class="badge bg-secondary">{{ m.type }}</span></td>
                        <td>{{ m.views | default(0) }}</td>
                        <td>
                            <a href="/admin/edit_movie/{{ m._id }}" class="btn btn-sm btn-primary"><i class="fas fa-edit"></i> Edit</a>
                            <a href="/admin/delete_movie/{{ m._id }}" class="btn btn-sm btn-outline-danger" onclick="return confirm('Are you sure?')"><i class="fas fa-trash"></i></a>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
    """).replace('<!-- SCRIPTS_BLOCK -->', """
    <script>
        function filterTable() {
            let input = document.getElementById("searchInput").value.toLowerCase();
            let rows = document.querySelectorAll("#movieTable tbody tr");
            rows.forEach(row => { row.style.display = row.innerText.toLowerCase().includes(input) ? "" : "none"; });
        }
        function toggleAll(source) {
            document.querySelectorAll('.movie-checkbox').forEach(cb => cb.checked = source.checked);
        }
        function deleteSelected() {
            let selected = [];
            document.querySelectorAll('.movie-checkbox:checked').forEach(cb => selected.push(cb.value));
            if(selected.length > 0 && confirm("নির্বাচিত মুভিগুলো ডিলেট করতে চান?")) {
                fetch('/admin/delete_multiple', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ids: selected}) })
                .then(() => window.location.reload());
            } else if (selected.length === 0) { alert("কোনো মুভি সিলেক্ট করা হয়নি!"); }
        }
    </script>
    """)
    return render_admin(html, movies=movies)

@app.route('/admin/delete_movie/<id>')
@login_required
def delete_movie(id):
    clear_cache()
    movies_col.delete_one({"_id": ObjectId(id)})
    return redirect(url_for('all_movies'))

@app.route('/admin/delete_multiple', methods=['POST'])
@login_required
def delete_multiple():
    clear_cache()
    data = request.json
    ids = [ObjectId(i) for i in data.get('ids', [])]
    movies_col.delete_many({"_id": {"$in": ids}})
    return jsonify({"status": "success"})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
