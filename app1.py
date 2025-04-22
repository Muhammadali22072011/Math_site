from flask import Flask, request, jsonify, render_template, render_template_string, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
from jinja2 import DictLoader
from flask_login import UserMixin
import json
import math
import os
import re
from datetime import datetime
from functools import wraps
from markupsafe import Markup
from flask_migrate import Migrate

app = Flask(__name__)
app.config['SECRET_KEY'] = 'секрет'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
db = SQLAlchemy(app)
migrate = Migrate(app, db)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'

app.jinja_env.globals.update(json=json, math=math)
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Модели
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(256), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    xp = db.Column(db.Integer, default=0)
    level = db.Column(db.Integer, default=1)
    coins = db.Column(db.Integer, default=0)
    titles = db.Column(db.String(500), default="[]")  # JSON список титулов
    inventory = db.Column(db.String(1000), default="[]")  # JSON список предметов
    equipped_title = db.Column(db.Integer)  # ID текущего титула
    achievements = db.relationship('UserAchievement', backref='user', lazy=True)
    daily_tasks = db.relationship('UserDailyTask', backref='user', lazy=True)
    streak = db.relationship('UserStreak', backref='user', lazy=True, uselist=False)
    friends = db.Column(db.String(1000), default="[]")  # JSON список ID друзей
    friend_requests = db.Column(db.String(1000), default="[]")  # JSON список входящих запросов
    notes = db.Column(db.Text)  # Пользовательские заметки
    settings = db.Column(db.String(1000), default="{}")  # JSON настройки пользователя

    def set_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)

    def add_xp(self, amount):
        self.xp += amount
        needed_xp = self.calculate_needed_xp()
        while self.xp >= needed_xp:
            self.xp -= needed_xp
            self.level += 1
            flash(f"Поздравляем! Вы достигли уровня {self.level}!", "success")
            needed_xp = self.calculate_needed_xp()
        db.session.commit()

    def calculate_needed_xp(self):
        return 100 * (self.level ** 2)

    def add_coins(self, amount):
        self.coins += amount
        db.session.commit()

    def add_title(self, title_id):
        try:
            titles = json.loads(self.titles)
            if title_id not in titles:
                titles.append(title_id)
                self.titles = json.dumps(titles)
                db.session.commit()
                return True
            return False
        except json.JSONDecodeError:
            self.titles = json.dumps([title_id])
            db.session.commit()
            return True

    def add_item(self, item_id):
        try:
            inventory = json.loads(self.inventory)
            if item_id not in inventory:
                inventory.append(item_id)
                self.inventory = json.dumps(inventory)
                db.session.commit()
                return True
            return False
        except json.JSONDecodeError:
            self.inventory = json.dumps([item_id])
            db.session.commit()
            return True

    def add_friend(self, friend_id):
        try:
            friends = json.loads(self.friends)
            if friend_id not in friends:
                friends.append(friend_id)
                self.friends = json.dumps(friends)
                db.session.commit()
                return True
            return False
        except json.JSONDecodeError:
            self.friends = json.dumps([friend_id])
            db.session.commit()
            return True

    def add_friend_request(self, user_id):
        try:
            requests = json.loads(self.friend_requests)
            if user_id not in requests:
                requests.append(user_id)
                self.friend_requests = json.dumps(requests)
                db.session.commit()
                return True
            return False
        except json.JSONDecodeError:
            self.friend_requests = json.dumps([user_id])
            db.session.commit()
            return True

    def update_streak(self):
        if not self.streak:
            self.streak = UserStreak(user_id=self.id)
            db.session.add(self.streak)
        
        now = datetime.utcnow()
        last_activity = self.streak.last_activity
        
        if (now - last_activity).days == 1:
            self.streak.current_streak += 1
            if self.streak.current_streak > self.streak.longest_streak:
                self.streak.longest_streak = self.streak.current_streak
        elif (now - last_activity).days > 1:
            self.streak.current_streak = 1
        
        self.streak.last_activity = now
        db.session.commit()

class Test(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    subject = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text)
    content = db.Column(db.Text)
    questions = db.relationship('Question', backref='test', lazy=True)
    xp_reward = db.Column(db.Integer, default=10)
    coin_reward = db.Column(db.Integer, default=5)
    title_reward = db.Column(db.Integer)  # ID титула за прохождение

class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    test_id = db.Column(db.Integer, db.ForeignKey('test.id'), nullable=False)
    text = db.Column(db.Text, nullable=False)
    answer_type = db.Column(db.String(20))
    options = db.Column(db.Text)
    correct_answer = db.Column(db.Text)
    figure_data = db.Column(db.Text)

class UserProgress(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    test_id = db.Column(db.Integer, db.ForeignKey('test.id'))
    score = db.Column(db.Float)
    completed_at = db.Column(db.DateTime, default=datetime.utcnow)
    test = db.relationship('Test')

class ShopItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Integer, nullable=False)
    item_type = db.Column(db.String(20))  # 'title', 'badge', 'background'
    image_url = db.Column(db.String(200))

class Achievement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    icon = db.Column(db.String(200))
    xp_reward = db.Column(db.Integer, default=0)
    coin_reward = db.Column(db.Integer, default=0)
    condition_type = db.Column(db.String(50))  # test_completed, perfect_score, streak, etc.
    condition_value = db.Column(db.Integer)    # value needed to unlock
    users = db.relationship('UserAchievement', backref='achievement', lazy=True)

class UserAchievement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    achievement_id = db.Column(db.Integer, db.ForeignKey('achievement.id'), nullable=False)
    earned_at = db.Column(db.DateTime, default=datetime.utcnow)
    progress = db.Column(db.Integer, default=0)

class DailyTask(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    xp_reward = db.Column(db.Integer, default=0)
    coin_reward = db.Column(db.Integer, default=0)
    task_type = db.Column(db.String(50))  # complete_test, get_perfect_score, etc.
    task_value = db.Column(db.Integer)    # number of times to complete
    active = db.Column(db.Boolean, default=True)

class UserDailyTask(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    task_id = db.Column(db.Integer, db.ForeignKey('daily_task.id'), nullable=False)
    completed_at = db.Column(db.DateTime)
    progress = db.Column(db.Integer, default=0)

class UserStreak(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    current_streak = db.Column(db.Integer, default=0)
    longest_streak = db.Column(db.Integer, default=0)
    last_activity = db.Column(db.DateTime, default=datetime.utcnow)

# Константы
TITLES = {
    1: {"name": "Новичок", "description": "Пройден первый тест"},
    2: {"name": "Математик", "description": "Пройдено 5 тестов"},
    3: {"name": "Гений", "description": "Пройдено 10 тестов"},
    4: {"name": "Геометр", "description": "Пройдено 3 теста по геометрии"},
    5: {"name": "Алгебраист", "description": "Пройдено 3 теста по алгебре"},
    6: {"name": "Мастер", "description": "Пройдено 15 тестов"},
    7: {"name": "Эксперт", "description": "Пройдено 25 тестов"},
    8: {"name": "Легенда", "description": "Пройдено 50 тестов"},
    9: {"name": "Король математики", "description": "Пройдено 100 тестов"},
    10: {"name": "Быстрый ученик", "description": "Пройдено 5 тестов с результатом выше 90%"},
    # ... остальные 40 титулов
}

# Вспомогательные функции
def get_current_user():
    if 'user_id' in session:
        return User.query.get(session['user_id'])
    return None

@app.context_processor
def inject_user():
    current_user = get_current_user()
    titles_data = []
    if current_user:
        titles = json.loads(current_user.titles)
        titles_data = [{"id": tid, **TITLES.get(tid, {"name": f"Титул {tid}", "description": "Неизвестный титул"})} for tid in titles]
    
    return dict(
        current_user=current_user,
        user_titles=titles_data,
        TITLES=TITLES,
        shop_items=ShopItem.query.all()
    )

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if not user or not user.is_admin:
            flash("Доступ только для администратора.", "danger")
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return decorated_function

class TestLanguageParser:
    def __init__(self, content):
        if not content or not isinstance(content, str):
            raise ValueError("Test content must be a non-empty string")
        self.content = content
        self.metadata = {'title': 'Без названия', 'subject': 'general', 'description': '', 'xp_reward': 10, 'coin_reward': 5, 'title_reward': None}
        self.sections = []
        self.questions = []
        self.rules = []
        self.parse()

    def parse(self):
        try:
            lines = self.content.split('\n')
            current_section = None

            for line in lines:
                line = line.strip()
                if not line:
                    continue

                if line.startswith('@test:'):
                    self.metadata['title'] = line[6:].strip()
                elif line.startswith('@subject:'):
                    subject = line[9:].strip()
                    if subject not in ['algebra', 'geometry', 'calculus']:
                        raise ValueError(f"Invalid subject: {subject}")
                    self.metadata['subject'] = subject
                elif line.startswith('@description:'):
                    self.metadata['description'] = line[13:].strip()
                elif line.startswith('@xp_reward:'):
                    try:
                        self.metadata['xp_reward'] = int(line[11:].strip())
                    except ValueError:
                        raise ValueError("XP reward must be an integer")
                elif line.startswith('@coin_reward:'):
                    try:
                        self.metadata['coin_reward'] = int(line[13:].strip())
                    except ValueError:
                        raise ValueError("Coin reward must be an integer")
                elif line.startswith('@title_reward:'):
                    try:
                        title_id = line[14:].strip()
                        self.metadata['title_reward'] = int(title_id) if title_id else None
                    except ValueError:
                        raise ValueError("Title reward must be an integer")
                elif line.startswith('## '):
                    if current_section and current_section['type'] == 'theory':
                        current_section['content'] += "\n" + line[3:]
                    else:
                        current_section = {'type': 'theory', 'title': line[3:], 'content': ''}
                        self.sections.append(current_section)
                        self.rules.append(line[3:].strip())
                elif line.startswith('<figure '):
                    figure_data = self.parse_figure(line)
                    if figure_data:
                        if current_section and current_section['type'] == 'theory':
                            current_section['content'] += "\n" + str(figure_data)
                        else:
                            self.sections.append({'type': 'figure', 'data': figure_data})
                        self.rules.append(figure_data)
                elif line.startswith('== '):
                    current_section = None
                    question_text = line[3:].strip(' =')
                    if not question_text:
                        raise ValueError("Question text cannot be empty")
                    self.questions.append({
                        'text': question_text,
                        'answer_type': None,
                        'options': None,
                        'correct_answer': None,
                        'figure': None
                    })
                elif line.startswith('[answer ') and self.questions:
                    answer_data = self.parse_answer(line)
                    if answer_data:
                        self.questions[-1].update(answer_data)
                elif current_section and current_section['type'] == 'theory':
                    current_section['content'] += "\n" + line
                    if self.rules and isinstance(self.rules[-1], str):
                        self.rules[-1] += " " + line

            # Validate that all questions have answers
            for i, q in enumerate(self.questions, 1):
                if not q.get('answer_type') or not q.get('correct_answer'):
                    raise ValueError(f"Question {i} is missing answer type or correct answer")

        except Exception as e:
            raise ValueError(f"Error parsing test content: {str(e)}")

    def parse_figure(self, line):
        try:
            figure_type = re.search(r'type="([^"]+)"', line).group(1)
            params = {}

            if figure_type == 'circle':
                radius = float(re.search(r'radius="([^"]+)"', line).group(1))
                params = {'radius': radius}
                area = math.pi * radius ** 2
                circumference = 2 * math.pi * radius
                return {
                    'type': 'figure',
                    'figure': 'circle',
                    'params': params,
                    'formulas': [
                        f'Площадь: S = π × r² = {area:.2f}',
                        f'Длина окружности: C = 2πr = {circumference:.2f}'
                    ]
                }

            elif figure_type == 'triangle':
                sides = re.search(r'sides="([^"]+)"', line).group(1).split(',')
                a, b, c = map(float, sides)
                params = {'a': a, 'b': b, 'c': c}
                s = (a + b + c) / 2
                area = math.sqrt(s * (s - a) * (s - b) * (s - c))
                return {
                    'type': 'figure',
                    'figure': 'triangle',
                    'params': params,
                    'formulas': [
                        f'Площадь (Герон): S = √[p(p-a)(p-b)(p-c)] = {area:.2f}',
                        f'Периметр: P = a + b + c = {a + b + c}'
                    ]
                }

            elif figure_type == 'square':
                side = float(re.search(r'side="([^"]+)"', line).group(1))
                params = {'side': side}
                area = side ** 2
                perimeter = 4 * side
                return {
                    'type': 'figure',
                    'figure': 'square',
                    'params': params,
                    'formulas': [
                        f'Площадь: S = a² = {area}',
                        f'Периметр: P = 4a = {perimeter}'
                    ]
                }

            elif figure_type == 'rectangle':
                length = float(re.search(r'length="([^"]+)"', line).group(1))
                width = float(re.search(r'width="([^"]+)"', line).group(1))
                params = {'length': length, 'width': width}
                area = length * width
                perimeter = 2 * (length + width)
                return {
                    'type': 'figure',
                    'figure': 'rectangle',
                    'params': params,
                    'formulas': [
                        f'Площадь: S = a × b = {area}',
                        f'Периметр: P = 2(a + b) = {perimeter}'
                    ]
                }

        except Exception as e:
            print(f"Ошибка при разборе фигуры: {e}")
            return None

    def parse_answer(self, line):
        try:
            answer_type = re.search(r'type="([^"]+)"', line).group(1)
            result = {'answer_type': answer_type}

            if answer_type == 'multiple_choice':
                options = re.search(r'options="([^"]+)"', line)
                if options:
                    result['options'] = [opt.strip() for opt in options.group(1).split('|')]
                correct = re.search(r'correct="([^"]+)"', line)
                if correct:
                    result['correct_answer'] = [ans.strip() for ans in correct.group(1).split('|')]

            elif answer_type in ['number', 'text']:
                correct = re.search(r'correct="([^"]+)"', line)
                if correct:
                    result['correct_answer'] = correct.group(1).strip()

            return result

        except Exception as e:
            print(f"Ошибка при разборе ответа: {e}")
            return None

def calculate_score(user_answers, questions):
    if not questions:
        return 0, []
        
    correct = 0
    results = []
    
    for q in questions:
        q_id = str(q.id) if hasattr(q, 'id') else str(questions.index(q) + 1)
        if q_id in user_answers:
            user_answer = user_answers[q_id]
            correct_answer = json.loads(q.correct_answer) if hasattr(q, 'correct_answer') else q.get('correct_answer')
            
            is_correct = False
            if q.answer_type == 'multiple_choice':
                is_correct = set(user_answer) == set(correct_answer)
            else:
                try:
                    user_num = float(user_answer)
                    correct_num = float(correct_answer)
                    is_correct = abs(user_num - correct_num) < 0.01
                except:
                    is_correct = str(user_answer).strip().lower() == str(correct_answer).strip().lower()
            
            if is_correct:
                correct += 1
            results.append({
                'question_id': q.id if hasattr(q, 'id') else questions.index(q) + 1,
                'is_correct': is_correct,
                'user_answer': user_answer,
                'correct_answer': correct_answer
            })
    
    score = round((correct / len(questions)) * 100, 2) if questions else 0
    return score, results

def render_figure(figure_data):
    if not figure_data or not isinstance(figure_data, dict):
        return ""
    
    figure_type = figure_data.get('figure')
    params = figure_data.get('params', {})
    
    if figure_type == 'circle':
        radius = params.get('radius', 50)
        return f'''
        <div class="figure-container">
            <svg width="200" height="200" viewBox="0 0 200 200">
                <circle cx="100" cy="100" r="{radius}" stroke="blue" fill="none" stroke-width="2"/>
                <line x1="100" y1="100" x2="{100 + radius}" y2="100" stroke="red" stroke-width="1"/>
                <text x="{100 + radius/2}" y="90" fill="red" font-size="12">r = {params.get('radius')}</text>
            </svg>
        </div>
        '''
        
    elif figure_type == 'triangle':
        a, b, c = params.get('a', 60), params.get('b', 80), params.get('c', 100)
        return f'''
        <div class="figure-container">
            <svg width="200" height="200" viewBox="0 0 200 200">
                <polygon points="50,180 150,180 100,50" stroke="blue" fill="none" stroke-width="2"/>
                <text x="50" y="190" font-size="12">a = {a}</text>
                <text x="150" y="190" font-size="12">b = {b}</text>
                <text x="100" y="40" font-size="12">c = {c}</text>
            </svg>
        </div>
        '''
        
    elif figure_type == 'square':
        side = params.get('side', 80)
        return f'''
        <div class="figure-container">
            <svg width="200" height="200" viewBox="0 0 200 200">
                <rect x="60" y="60" width="{side}" height="{side}" stroke="blue" fill="none" stroke-width="2"/>
                <text x="{60 + side/2}" y="160" font-size="12">a = {side}</text>
            </svg>
        </div>
        '''
        
    elif figure_type == 'rectangle':
        length = params.get('length', 100)
        width = params.get('width', 60)
        return f'''
        <div class="figure-container">
            <svg width="200" height="200" viewBox="0 0 200 200">
                <rect x="50" y="70" width="{length}" height="{width}" stroke="blue" fill="none" stroke-width="2"/>
                <text x="{50 + length/2}" y="160" font-size="12">a = {length}</text>
                <text x="20" y="{70 + width/2}" font-size="12">b = {width}</text>
            </svg>
        </div>
        '''
    
    return ""

# Шаблоны
TEMPLATES = {
    'base.html': '''
    <!DOCTYPE html>
    <html lang="ru" data-theme="light">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{% block title %}{% endblock %} - Математическая платформа</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
        <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
        <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700&display=swap" rel="stylesheet">
        <style>
            :root {
                --primary-color: #2196F3;
                --secondary-color: #1976D2;
                --accent-color: #FF4081;
                --text-color: #333333;
                --light-bg: #F5F5F5;
                --dark-bg: #1E1E1E;
                --success-color: #4CAF50;
                --warning-color: #FFC107;
                --danger-color: #F44336;
                --card-bg: #FFFFFF;
                --border-color: #E0E0E0;
                --shadow-color: rgba(0,0,0,0.1);
                --sidebar-width: 250px;
            }
            
            [data-theme="dark"] {
                --primary-color: #64B5F6;
                --secondary-color: #42A5F5;
                --accent-color: #FF80AB;
                --text-color: #FFFFFF;
                --light-bg: #121212;
                --dark-bg: #000000;
                --success-color: #81C784;
                --warning-color: #FFD54F;
                --danger-color: #E57373;
                --card-bg: #1E1E1E;
                --border-color: #333333;
                --shadow-color: rgba(0,0,0,0.3);
            }
            
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            
            body {
                font-family: 'Montserrat', sans-serif;
                background-color: var(--light-bg);
                color: var(--text-color);
                min-height: 100vh;
                display: flex;
            }
            
            /* Боковое меню */
            .sidebar {
                width: var(--sidebar-width);
                background: linear-gradient(135deg, var(--primary-color), var(--secondary-color));
                color: white;
                padding: 1.5rem 0;
                position: fixed;
                height: 100vh;
                overflow-y: auto;
                transition: all 0.3s ease;
                z-index: 1000;
            }
            
            .sidebar-header {
                padding: 0 1.5rem;
                margin-bottom: 2rem;
                display: flex;
                align-items: center;
                gap: 1rem;
            }
            
            .sidebar-brand {
                font-size: 1.5rem;
                font-weight: 700;
                color: white;
                text-decoration: none;
                display: flex;
                align-items: center;
                gap: 0.5rem;
            }
            
            .sidebar-brand i {
                font-size: 1.8rem;
                color: var(--warning-color);
            }
            
            .nav-link {
                color: rgba(255,255,255,0.9);
                padding: 1rem 1.5rem;
                display: flex;
                align-items: center;
                gap: 1rem;
                font-weight: 500;
                transition: all 0.3s ease;
                border-left: 4px solid transparent;
            }
            
            .nav-link:hover {
                color: white;
                background: rgba(255,255,255,0.1);
                border-left-color: var(--warning-color);
            }
            
            .nav-link.active {
                color: white;
                background: rgba(255,255,255,0.15);
                border-left-color: var(--warning-color);
            }
            
            .nav-link i {
                font-size: 1.2rem;
                width: 24px;
                text-align: center;
            }
            
            /* Основной контент */
            .main-content {
                flex: 1;
                margin-left: var(--sidebar-width);
                padding: 2rem;
                transition: all 0.3s ease;
            }
            
            /* Верхняя панель */
            .top-bar {
                background: var(--card-bg);
                padding: 1rem 2rem;
                margin: -2rem -2rem 2rem -2rem;
                box-shadow: 0 2px 10px var(--shadow-color);
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            
            .user-info {
                display: flex;
                align-items: center;
                gap: 1rem;
            }
            
            .user-avatar {
                width: 40px;
                height: 40px;
                border-radius: 50%;
                background: linear-gradient(135deg, var(--secondary-color), var(--primary-color));
                display: flex;
                align-items: center;
                justify-content: center;
                color: white;
                font-weight: 700;
                box-shadow: 0 3px 10px var(--shadow-color);
            }
            
            .user-stats {
                display: flex;
                gap: 1rem;
            }
            
            .stat-item {
                background: var(--light-bg);
                padding: 0.5rem 1rem;
                border-radius: 20px;
                display: flex;
                align-items: center;
                gap: 0.5rem;
                font-size: 0.9rem;
            }
            
            .stat-item i {
                color: var(--warning-color);
            }
            
            /* Кнопки */
            .btn {
                border-radius: 20px;
                padding: 0.7rem 1.5rem;
                font-weight: 500;
                transition: all 0.3s ease;
            }
            
            .btn-primary {
                background: linear-gradient(135deg, var(--secondary-color), var(--primary-color));
                border: none;
            }
            
            .btn-primary:hover {
                transform: translateY(-2px);
                box-shadow: 0 5px 15px var(--shadow-color);
            }
            
            .btn-outline-light {
                border: 2px solid white;
            }
            
            .btn-outline-light:hover {
                background: white;
                color: var(--primary-color);
            }
            
            /* Flash сообщения */
            .flash-messages {
                position: fixed;
                top: 20px;
                right: 20px;
                z-index: 1000;
            }
            
            .flash-message {
                animation: slideIn 0.3s ease-out;
                border-radius: 10px;
                box-shadow: 0 3px 10px var(--shadow-color);
                border: none;
            }
            
            @keyframes slideIn {
                from { transform: translateX(100%); opacity: 0; }
                to { transform: translateX(0); opacity: 1; }
            }
            
            /* Адаптивность */
            @media (max-width: 768px) {
                .sidebar {
                    transform: translateX(-100%);
                }
                
                .sidebar.active {
                    transform: translateX(0);
                }
                
                .main-content {
                    margin-left: 0;
                }
                
                .top-bar {
                    padding: 1rem;
                }
                
                .user-stats {
                    display: none;
                }
            }
            
            /* Мобильное меню */
            .mobile-menu-btn {
                display: none;
                background: none;
                border: none;
                color: var(--text-color);
                font-size: 1.5rem;
                cursor: pointer;
            }
            
            @media (max-width: 768px) {
                .mobile-menu-btn {
                    display: block;
                }
            }
            
            /* Анимации */
            .fade-in {
                animation: fadeIn 0.5s ease-out;
            }
            
            @keyframes fadeIn {
                from { opacity: 0; transform: translateY(20px); }
                to { opacity: 1; transform: translateY(0); }
            }
        </style>
        {% block extra_css %}{% endblock %}
    </head>
    <body>
        <!-- Боковое меню -->
        <nav class="sidebar">
            <div class="sidebar-header">
                <a href="{{ url_for('index') }}" class="sidebar-brand">
                    <i class="fas fa-calculator"></i>
                    <span>Математика</span>
                </a>
            </div>
            
            <ul class="nav flex-column">
                <li class="nav-item">
                    <a class="nav-link {% if request.endpoint == 'index' %}active{% endif %}" href="{{ url_for('index') }}">
                        <i class="fas fa-home"></i>
                        <span>Главная</span>
                    </a>
                </li>
                <li class="nav-item">
                    <a class="nav-link {% if request.endpoint == 'tests' %}active{% endif %}" href="{{ url_for('tests') }}">
                        <i class="fas fa-list"></i>
                        <span>Тесты</span>
                    </a>
                </li>
                <li class="nav-item">
                    <a class="nav-link {% if request.endpoint == 'achievements' %}active{% endif %}" href="{{ url_for('achievements') }}">
                        <i class="fas fa-trophy"></i>
                        <span>Достижения</span>
                    </a>
                </li>
                <li class="nav-item">
                    <a class="nav-link {% if request.endpoint == 'daily_tasks' %}active{% endif %}" href="{{ url_for('daily_tasks') }}">
                        <i class="fas fa-tasks"></i>
                        <span>Задания</span>
                    </a>
                </li>
                <li class="nav-item">
                    <a class="nav-link {% if request.endpoint == 'friends' %}active{% endif %}" href="{{ url_for('friends') }}">
                        <i class="fas fa-users"></i>
                        <span>Друзья</span>
                    </a>
                </li>
                <li class="nav-item">
                    <a class="nav-link {% if request.endpoint == 'leaderboard' %}active{% endif %}" href="{{ url_for('leaderboard') }}">
                        <i class="fas fa-chart-line"></i>
                        <span>Рейтинг</span>
                    </a>
                </li>
                <li class="nav-item">
                    <a class="nav-link {% if request.endpoint == 'shop' %}active{% endif %}" href="{{ url_for('shop') }}">
                        <i class="fas fa-shopping-cart"></i>
                        <span>Магазин</span>
                    </a>
                </li>
                {% if current_user.is_authenticated and current_user.is_admin %}
                <li class="nav-item">
                    <a class="nav-link {% if request.endpoint == 'admin_panel' %}active{% endif %}" href="{{ url_for('admin_panel') }}">
                        <i class="fas fa-cogs"></i>
                        <span>Админ-панель</span>
                    </a>
                </li>
                {% endif %}
            </ul>
        </nav>
        
        <!-- Основной контент -->
        <main class="main-content">
            <!-- Верхняя панель -->
            <div class="top-bar">
                <button class="mobile-menu-btn" onclick="toggleSidebar()">
                    <i class="fas fa-bars"></i>
                </button>
                
                {% if current_user.is_authenticated %}
                <div class="user-info">
                    <div class="user-avatar">
                        {{ current_user.username[0].upper() }}
                    </div>
                    <div>
                        <div class="fw-bold">{{ current_user.username }}</div>
                        <div class="small text-muted">Уровень {{ current_user.level }}</div>
                    </div>
                    <div class="user-stats">
                        <div class="stat-item">
                            <i class="fas fa-star"></i> {{ current_user.xp }} XP
                        </div>
                        <div class="stat-item">
                            <i class="fas fa-coins"></i> {{ current_user.coins }}
                        </div>
                    </div>
                    <a href="{{ url_for('logout') }}" class="btn btn-outline-danger ms-3">
                        <i class="fas fa-sign-out-alt"></i>
                    </a>
                </div>
                {% else %}
                <div>
                    <a href="{{ url_for('login') }}" class="btn btn-outline-primary me-2">Войти</a>
                    <a href="{{ url_for('register') }}" class="btn btn-primary">Регистрация</a>
                </div>
                {% endif %}
            </div>
            
            <!-- Flash сообщения -->
            <div class="flash-messages">
                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                        {% for category, message in messages %}
                            <div class="alert alert-{{ category }} alert-dismissible fade show flash-message" role="alert">
                                {{ message }}
                                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                            </div>
                        {% endfor %}
                    {% endif %}
                {% endwith %}
            </div>
            
            <!-- Контент страницы -->
            <div class="content fade-in">
                {% block content %}{% endblock %}
            </div>
        </main>
        
        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
        <script>
            // Переключение бокового меню на мобильных устройствах
            function toggleSidebar() {
                document.querySelector('.sidebar').classList.toggle('active');
            }
            
            // Автоматическое скрытие flash-сообщений
            document.addEventListener('DOMContentLoaded', function() {
                const alerts = document.querySelectorAll('.alert');
                alerts.forEach(function(alert) {
                    setTimeout(function() {
                        alert.classList.remove('show');
                        setTimeout(function() {
                            alert.remove();
                        }, 300);
                    }, 5000);
                });
            });
            
            // Закрытие бокового меню при клике вне его на мобильных устройствах
            document.addEventListener('click', function(event) {
                const sidebar = document.querySelector('.sidebar');
                const mobileMenuBtn = document.querySelector('.mobile-menu-btn');
                
                if (window.innerWidth <= 768 && 
                    !sidebar.contains(event.target) && 
                    !mobileMenuBtn.contains(event.target)) {
                    sidebar.classList.remove('active');
                }
            });
        </script>
        {% block extra_js %}{% endblock %}
    </body>
    </html>
    ''',
    
    'index.html': '''
    {% extends "base.html" %}
    {% block content %}
        <h1 class="mb-4">Добро пожаловать на образовательную платформу по математике!</h1>
        <div class="row">
            <div class="col-md-8">
                <div class="math-container">
                    <p>Изучайте математику в интерактивной форме:</p>
                    <ul>
                        <li>Проходите тесты с автоматической проверкой</li>
                        <li>Зарабатывайте опыт и повышайте уровень</li>
                        <li>Получайте виртуальные монеты за прохождение тестов</li>
                        <li>Покупайте уникальные титулы и предметы в магазине</li>
                        <li>Отслеживайте свой прогресс</li>
                    </ul>
                    {% if not current_user %}
                        <a href="/register" class="btn btn-primary">Начать обучение</a>
                    {% else %}
                        <a href="/tests" class="btn btn-success">К тестам</a>
                    {% endif %}
                </div>
            </div>
        </div>
    {% endblock %}
    ''',
    
    'register.html': '''
    {% extends "base.html" %}
    {% block title %}Регистрация{% endblock %}
    {% block content %}
        <h1>Регистрация</h1>
        <form method="post">
            <div class="mb-3">
                <label for="username" class="form-label">Имя пользователя</label>
                <input type="text" class="form-control" id="username" name="username" required>
            </div>
            <div class="mb-3">
                <label for="email" class="form-label">Email</label>
                <input type="email" class="form-control" id="email" name="email" required>
            </div>
            <div class="mb-3">
                <label for="password" class="form-label">Пароль</label>
                <input type="password" class="form-control" id="password" name="password" required>
            </div>
            <button type="submit" class="btn btn-primary">Зарегистрироваться</button>
        </form>
    {% endblock %}
    ''',
    
    'login.html': '''
    {% extends "base.html" %}
    {% block title %}Вход{% endblock %}
    {% block content %}
        <h1>Вход</h1>
        <form method="post">
            <div class="mb-3">
                <label for="username" class="form-label">Имя пользователя</label>
                <input type="text" class="form-control" id="username" name="username" required>
            </div>
            <div class="mb-3">
                <label for="password" class="form-label">Пароль</label>
                <input type="password" class="form-control" id="password" name="password" required>
            </div>
            <button type="submit" class="btn btn-primary">Войти</button>
        </form>
    {% endblock %}
    ''',
    
    'profile.html': '''
    {% extends "base.html" %}
    {% block title %}Профиль{% endblock %}
    {% block content %}
        <h1>Профиль пользователя {{ current_user.username }}</h1>
        
        {% if current_user.equipped_title %}
            <div class="alert alert-info">
                Ваш текущий титул: <strong>{{ TITLES[current_user.equipped_title]['name'] }}</strong>
            </div>
        {% endif %}
        
        <div class="row">
            <div class="col-md-4">
                <div class="card mb-4">
                    <div class="card-body">
                        <h5 class="card-title">Информация</h5>
                        <p class="card-text">Email: {{ current_user.email }}</p>
                        <p class="card-text">Дата регистрации: {{ current_user.created_at.strftime('%Y-%m-%d') }}</p>
                        <p class="card-text">Уровень: {{ current_user.level }}</p>
                        <div class="progress-bar">
                            <div class="progress-fill" style="width: {{ (current_user.xp / current_user.calculate_needed_xp()) * 100 }}%"></div>
                        </div>
                        <p class="card-text">Опыт: {{ current_user.xp }}/{{ current_user.calculate_needed_xp() }}</p>
                        <p class="card-text">Монеты: {{ current_user.coins }}</p>
                    </div>
                </div>
                
                <div class="card mb-4">
                    <div class="card-body">
                        <h5 class="card-title">Титулы ({{ user_titles|length }}/50)</h5>
                        {% if user_titles %}
                            <div style="max-height: 300px; overflow-y: auto;">
                                {% for title in user_titles %}
                                    <div class="title-badge">
                                        <strong>{{ title.name }}</strong>
                                        <small>{{ title.description }}</small>
                                        <form method="post" action="{{ url_for('equip_title', title_id=title.id) }}" style="display: inline;">
                                            <button type="submit" class="btn btn-sm btn-outline-primary">Надеть</button>
                                        </form>
                                    </div>
                                {% endfor %}
                            </div>
                        {% else %}
                            <p>У вас пока нет титулов</p>
                        {% endif %}
                    </div>
                </div>
            </div>
            
            <div class="col-md-8">
                <h2>Прогресс</h2>
                {% if progress %}
                    <div class="list-group">
                        {% for p in progress %}
                            <div class="list-group-item">
                                <h5>{{ p.test.title }}</h5>
                                <p>Оценка: {{ p.score }}%</p>
                                <small class="text-muted">Завершено: {{ p.completed_at.strftime('%Y-%m-%d %H:%M') }}</small>
                            </div>
                        {% endfor %}
                    </div>
                {% else %}
                    <p>Вы еще не прошли ни одного теста.</p>
                {% endif %}
            </div>
        </div>
    {% endblock %}
    ''',
    
    'tests.html': '''
    {% extends "base.html" %}
    {% block title %}Тесты{% endblock %}
    {% block content %}
        <h1>Доступные тесты</h1>
        
        <div class="mb-3">
            <a href="/tests?subject=algebra" class="btn btn-outline-primary">Алгебра</a>
            <a href="/tests?subject=geometry" class="btn btn-outline-primary">Геометрия</a>
            <a href="/tests" class="btn btn-outline-secondary">Все тесты</a>
        </div>
        
        {% if tests %}
            <div class="row">
                {% for test in tests %}
                    <div class="col-md-4 mb-4">
                        <div class="card">
                            <div class="card-body">
                                <h5 class="card-title">{{ test.title }}</h5>
                                <p class="card-text">{{ test.description }}</p>
                                <p class="text-muted">{{ test.subject|capitalize }}</p>
                                <p class="text-success">Награда: 
                                    {{ test.xp_reward }} XP, 
                                    {{ test.coin_reward }} монет
                                    {% if test.title_reward %} + титул{% endif %}
                                </p>
                                <a href="/test/{{ test.id }}" class="btn btn-primary">Начать тест</a>
                            </div>
                        </div>
                    </div>
                {% endfor %}
            </div>
        {% else %}
            <p>Нет доступных тестов.</p>
        {% endif %}
    {% endblock %}
    ''',
    
    'test.html': '''
    {% extends "base.html" %}
    {% block title %}{{ test.title }}{% endblock %}
    {% block content %}
    <h2>{{ parsed.title }}</h2>
    <p>{{ parsed.description }}</p>

    {% if parsed.rules %}
    <div class="alert alert-info">
      <ul>
        {% for rule in parsed.rules %}
          <li>{{ rule }}</li>
        {% endfor %}
      </ul>
    </div>
    {% endif %}

    {% for fig in parsed.figures %}
      {{ fig|safe }}
    {% endfor %}

        <form method="POST">
    {% for q in parsed.questions %}
        <div class="question-card">
            <strong>{{ loop.index }}. {{ q.text }}</strong><br>
            {% if q.answer_type == 'number' %}
                <input type="number" step="any" name="q{{ loop.index }}" class="form-control mt-2">
            {% elif q.answer_type == 'text' %}
                <input type="text" name="q{{ loop.index }}" class="form-control mt-2">
            {% elif q.answer_type == 'multiple_choice' %}
                {% for opt in q.options %}
                    <div><input type="checkbox" name="q{{ loop.index }}" value="{{ opt }}"> {{ opt }}</div>
                {% endfor %}
            {% endif %}
        </div>
    {% endfor %}
      <button type="submit" class="btn btn-success">Проверить</button>
    </form>
    {% endblock %}
    ''',
    
    'test_result.html': '''
    {% extends "base.html" %}
    {% block title %}Результаты теста{% endblock %}
    {% block content %}
        <div class="container mt-4">
            <h1>Результаты теста: {{ test.title }}</h1>
            
            <div class="alert alert-{{ 'success' if score >= 80 else 'warning' if score >= 50 else 'danger' }}">
                <h4>Ваш результат: {{ score }}%</h4>
                {% if xp_reward > 0 %}
                    <p>Получено опыта: +{{ xp_reward }}</p>
                {% endif %}
                {% if coin_reward > 0 %}
                    <p>Получено монет: +{{ coin_reward }}</p>
                {% endif %}
                {% if title_reward %}
                    <p>Получен новый титул: <strong>{{ TITLES[title_reward]['name'] }}</strong></p>
                {% endif %}
            </div>
            
            <h3>Детализация:</h3>
            {% for result in results %}
                <div class="card mb-2">
                    <div class="card-body">
                        <h5 class="card-title">Вопрос {{ loop.index }}</h5>
                        <p class="card-text">
                            {% if result.is_correct %}
                                <span class="text-success">✓ Правильно</span>
                            {% else %}
                                <span class="text-danger">✗ Неправильно</span>
                            {% endif %}
                        </p>
                        <p class="card-text">Ваш ответ: {{ result.user_answer }}</p>
                        {% if not result.is_correct %}
                            <p class="card-text">Правильный ответ: {{ result.correct_answer }}</p>
                        {% endif %}
                    </div>
                </div>
            {% endfor %}
            
            <a href="/tests" class="btn btn-primary">Вернуться к тестам</a>
        </div>
    {% endblock %}
    ''',
    
    'calculator.html': '''
    {% extends "base.html" %}
    {% block title %}Калькулятор{% endblock %}
    {% block content %}
        <h1>Математический калькулятор</h1>
        
        <div class="row">
            <div class="col-md-8">
                <div class="card">
                    <div class="card-body">
                        <h5 class="card-title">Введите выражение</h5>
                        <div class="mb-3">
                            <input type="text" class="form-control" id="expression" placeholder="Например: 2 + 2 * 2">
                        </div>
                        
                        <div class="calculator-buttons">
                            <button class="btn btn-secondary calc-btn" data-value="1">1</button>
                            <button class="btn btn-secondary calc-btn" data-value="2">2</button>
                            <button class="btn btn-secondary calc-btn" data-value="3">3</button>
                            <button class="btn btn-secondary calc-btn" data-value="+">+</button><br>
                            
                            <button class="btn btn-secondary calc-btn" data-value="4">4</button>
                            <button class="btn btn-secondary calc-btn" data-value="5">5</button>
                            <button class="btn btn-secondary calc-btn" data-value="6">6</button>
                            <button class="btn btn-secondary calc-btn" data-value="-">-</button><br>
                            
                            <button class="btn btn-secondary calc-btn" data-value="7">7</button>
                            <button class="btn btn-secondary calc-btn" data-value="8">8</button>
                            <button class="btn btn-secondary calc-btn" data-value="9">9</button>
                            <button class="btn btn-secondary calc-btn" data-value="*">*</button><br>
                            
                            <button class="btn btn-secondary calc-btn" data-value="0">0</button>
                            <button class="btn btn-secondary calc-btn" data-value=".">.</button>
                            <button class="btn btn-secondary calc-btn" data-value="/">/</button>
                            <button class="btn btn-secondary calc-btn" data-value="(">(</button>
                            <button class="btn btn-secondary calc-btn" data-value=")">)</button><br>
                            
                            <button class="btn btn-info calc-btn" data-value="sin(">sin</button>
                            <button class="btn btn-info calc-btn" data-value="cos(">cos</button>
                            <button class="btn btn-info calc-btn" data-value="tan(">tan</button>
                            <button class="btn btn-info calc-btn" data-value="sqrt(">√</button>
                            <button class="btn btn-info calc-btn" data-value="pi">π</button><br>
                            
                            <button class="btn btn-danger" id="clear-btn">Очистить</button>
                            <button id="calculate-btn" class="btn btn-primary">=</button>
                        </div>
                    </div>
                </div>
            </div>
            <div class="col-md-4">
                <div class="card">
                    <div class="card-body">
                        <h5 class="card-title">Результат</h5>
                        <div id="result" class="math-container" style="min-height: 100px;">
                            Результат появится здесь...
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <style>
            .calculator-buttons .btn {
                margin: 2px;
                min-width: 40px;
            }
        </style>
        
        <script>
            document.querySelectorAll('.calc-btn').forEach(btn => {
                btn.addEventListener('click', function() {
                    const exprInput = document.getElementById('expression');
                    exprInput.value += this.getAttribute('data-value');
                });
            });
            
            document.getElementById('clear-btn').addEventListener('click', function() {
                document.getElementById('expression').value = '';
                document.getElementById('result').innerHTML = 'Результат появится здесь...';
            });
            
            document.getElementById('calculate-btn').addEventListener('click', function() {
                const expression = document.getElementById('expression').value;
                fetch('/api/calculate', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ expression: expression })
                })
                .then(response => response.json())
                .then(data => {
                    const resultDiv = document.getElementById('result');
                    if (data.error) {
                        resultDiv.innerHTML = `<div class="alert alert-danger">Ошибка: ${data.error}</div>`;
                    } else {
                        resultDiv.innerHTML = `<h4>${expression} = ${data.result}</h4>`;
                        MathJax.typeset();
                    }
                });
            });
        </script>
    {% endblock %}
    ''',
    
    'shop.html': '''
    {% extends "base.html" %}
    {% block title %}Магазин{% endblock %}
    {% block content %}
        <h1>Магазин</h1>
        
        <div class="row">
            <div class="col-md-3">
                <div class="card mb-4">
                    <div class="card-body">
                        <h5 class="card-title">Ваш баланс</h5>
                        <p class="card-text">
                            <strong>Монеты:</strong> {{ current_user.coins }}<br>
                            <strong>Уровень:</strong> {{ current_user.level }}<br>
                            <strong>Опыт:</strong> {{ current_user.xp }}/{{ current_user.calculate_needed_xp() }}
                        </p>
                    </div>
                </div>
            </div>
            
            <div class="col-md-9">
                <div class="row">
                    {% for item in shop_items %}
                        <div class="col-md-4 mb-4">
                            <div class="card h-100">
                                <div class="card-body d-flex flex-column">
                                    <h5 class="card-title">{{ item.name }}</h5>
                                    <p class="card-text">{{ item.description }}</p>
                                    <p class="text-muted mt-auto">Цена: {{ item.price }} монет</p>
                                    <form method="post" action="{{ url_for('buy_item', item_id=item.id) }}" class="mt-auto">
                                        <button type="submit" class="btn btn-primary w-100" 
                                            {% if current_user.coins < item.price %}disabled{% endif %}>
                                            Купить
                                        </button>
                                    </form>
                                </div>
                            </div>
                        </div>
                    {% endfor %}
                </div>
            </div>
        </div>
    {% endblock %}
    ''',
    
    'admin.html': '''
{% extends "base.html" %}

{% block content %}
<style>
    .admin-panel {
        font-family: 'Segoe UI', sans-serif;
        background: linear-gradient(to bottom right, #eef1f5, #dbeafe);
        padding: 2rem;
        border-radius: 16px;
        box-shadow: 0 10px 25px rgba(0,0,0,0.1);
    }
    .admin-panel h2 {
        font-weight: bold;
        font-size: 2rem;
        color: #1f2937;
    }
    .admin-section {
        margin-top: 2rem;
    }
    table {
        width: 100%;
        background-color: white;
        border-collapse: collapse;
        border-radius: 12px;
        overflow: hidden;
        box-shadow: 0 4px 10px rgba(0,0,0,0.05);
    }
    th, td {
        padding: 12px 18px;
        border-bottom: 1px solid #eee;
        text-align: left;
    }
    th {
        background-color: #3b82f6;
        color: white;
        text-transform: uppercase;
        font-size: 0.85rem;
    }
    tr:hover {
        background-color: #f3f4f6;
    }
    .btn {
        margin: 2px;
        border-radius: 6px;
        font-size: 0.8rem;
    }
    .form-control-sm {
        width: 150px;
        display: inline-block;
    }
</style>

<div class="admin-panel">
    <h2>Админ-панель</h2>

    <div class="admin-section">
        <h4>Пользователи</h4>
        <table>
            <thead>
                <tr>
                    <th>ID</th>
                    <th>Логин</th>
                    <th>Email</th>
                    <th>Уровень</th>
                    <th>Монеты</th>
                    <th>Админ</th>
                    <th>Дата</th>
                    <th>Действия</th>
                </tr>
            </thead>
            <tbody>
                {% for user in users %}
                <tr>
                    <td>{{ user.id }}</td>
                    <td>{{ user.username }}</td>
                    <td>{{ user.email }}</td>
                    <td>{{ user.level }}</td>
                    <td>{{ user.coins }}</td>
                    <td>{% if user.is_admin %}Да{% else %}Нет{% endif %}</td>
                    <td>{{ user.created_at.strftime("%d.%m.%Y") }}</td>
                    <td>
                        <form action="/admin/delete_user/{{ user.id }}" method="post" style="display:inline;">
                            <button class="btn btn-danger btn-sm">Удалить</button>
                        </form>
                        <form action="/admin/reset_password/{{ user.id }}" method="post" style="display:inline;">
                            <button class="btn btn-warning btn-sm">Сбросить пароль</button>
                        </form>
                        <form action="/admin/toggle_admin/{{ user.id }}" method="post" style="display:inline;">
                            <button class="btn btn-secondary btn-sm">
                                {% if user.is_admin %}Убрать админа{% else %}Сделать админом{% endif %}
                            </button>
                        </form>
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>

    <div class="admin-section">
        <h4>Тесты</h4>
        <table>
            <thead>
                <tr>
                    <th>ID</th>
                    <th>Название</th>
                    <th>Предмет</th>
                    <th>Награда (XP/монеты)</th>
                    <th>Титул</th>
                    <th>Действия</th>
                </tr>
            </thead>
            <tbody>
                {% for test in tests %}
                <tr>
                    <td>{{ test.id }}</td>
                    <td>{{ test.title }}</td>
                    <td>{{ test.subject }}</td>
                    <td>{{ test.xp_reward }}/{{ test.coin_reward }}</td>
                    <td>{% if test.title_reward %}{{ TITLES[test.title_reward]['name'] }}{% else %}Нет{% endif %}</td>
                    <td>
                        <form action="/admin/delete_test/{{ test.id }}" method="post" style="display:inline;">
                            <button class="btn btn-danger btn-sm">Удалить</button>
                        </form>
                        <a href="/admin/edit_test/{{ test.id }}" class="btn btn-info btn-sm">Редактировать</a>
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        <a href="/admin/create_test" class="btn btn-primary mt-3">Создать новый тест</a>
    </div>

    <div class="admin-section">
        <h4>Магазин</h4>
        <table>
            <thead>
                <tr>
                    <th>ID</th>
                    <th>Название</th>
                    <th>Тип</th>
                    <th>Цена</th>
                    <th>Действия</th>
                </tr>
            </thead>
            <tbody>
                {% for item in shop_items %}
                <tr>
                    <td>{{ item.id }}</td>
                    <td>{{ item.name }}</td>
                    <td>{{ item.item_type }}</td>
                    <td>{{ item.price }}</td>
                    <td>
                        <form action="/admin/delete_shop_item/{{ item.id }}" method="post" style="display:inline;">
                            <button class="btn btn-danger btn-sm">Удалить</button>
                        </form>
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        <a href="/admin/create_shop_item" class="btn btn-primary mt-3">Добавить товар</a>
    </div>
</div>
{% endblock %}
    ''',

    'create_test.html': '''
    {% extends "base.html" %}
    {% block title %}Создать тест{% endblock %}
    {% block content %}
    <div class="container mt-4">
        <div class="card shadow-lg">
            <div class="card-header bg-primary text-white">
                <h2 class="mb-0">Создание нового теста</h2>
            </div>
            <div class="card-body">
                <form method="post" id="testForm">
                    <div class="row">
                        <div class="col-md-6">
                            <div class="mb-3">
                                <label for="title" class="form-label">Название теста</label>
                                <input type="text" class="form-control" id="title" name="title" required>
                            </div>
                            
                            <div class="mb-3">
                                <label for="subject" class="form-label">Предмет</label>
                                <select class="form-select" id="subject" name="subject" required>
                                    <option value="algebra">Алгебра</option>
                                    <option value="geometry">Геометрия</option>
                                    <option value="calculus">Математический анализ</option>
                                </select>
                            </div>
                            
                            <div class="mb-3">
                                <label for="description" class="form-label">Описание</label>
                                <textarea class="form-control" id="description" name="description" rows="3"></textarea>
                            </div>
                        </div>
                        
                        <div class="col-md-6">
                            <div class="mb-3">
                                <label for="xp_reward" class="form-label">Опыт за прохождение</label>
                                <input type="number" class="form-control" id="xp_reward" name="xp_reward" value="10" min="0">
                            </div>
                            
                            <div class="mb-3">
                                <label for="coin_reward" class="form-label">Монеты за прохождение</label>
                                <input type="number" class="form-control" id="coin_reward" name="coin_reward" value="5" min="0">
                            </div>
                            
                            <div class="mb-3">
                                <label for="title_reward" class="form-label">Титул за прохождение</label>
                                <select class="form-select" id="title_reward" name="title_reward">
                                    <option value="">Не выдавать титул</option>
                                    {% for id, title in TITLES.items() %}
                                        <option value="{{ id }}">{{ title.name }}</option>
                                    {% endfor %}
                                </select>
                            </div>
                        </div>
                    </div>

                    <div class="mb-4">
                        <h4 class="mb-3">Содержимое теста</h4>
                        <div class="card">
                            <div class="card-body">
                                <div class="d-flex justify-content-between mb-3">
                                    <div class="btn-group">
                                        <button type="button" class="btn btn-outline-primary" onclick="addTheorySection()">
                                            <i class="fas fa-book"></i> Теория
                                        </button>
                                        <button type="button" class="btn btn-outline-success" onclick="addQuestion()">
                                            <i class="fas fa-question"></i> Вопрос
                                        </button>
                                        <button type="button" class="btn btn-outline-info" onclick="showFigureModal()">
                                            <i class="fas fa-shapes"></i> Фигура
                                        </button>
                                    </div>
                                    <button type="button" class="btn btn-outline-secondary" onclick="previewTest()">
                                        <i class="fas fa-eye"></i> Предпросмотр
                                    </button>
                                </div>
                                
                                <div id="testContent" class="test-content">
                                    <textarea class="form-control" id="content" name="content" rows="20" required></textarea>
                                </div>
                            </div>
                        </div>
                    </div>

                    <button type="submit" class="btn btn-primary">
                        <i class="fas fa-save"></i> Создать тест
                    </button>
                </form>
            </div>
        </div>
    </div>

    <!-- Модальное окно для создания фигур -->
    <div class="modal fade" id="figureModal" tabindex="-1">
        <div class="modal-dialog modal-lg">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title">Создание фигуры</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    <div class="row">
                        <div class="col-md-6">
                            <div class="mb-3">
                                <label class="form-label">Тип фигуры</label>
                                <select class="form-select" id="figureType">
                                    <option value="circle">Круг</option>
                                    <option value="triangle">Треугольник</option>
                                    <option value="square">Квадрат</option>
                                    <option value="rectangle">Прямоугольник</option>
                                    <option value="polygon">Многоугольник</option>
                                </select>
                            </div>
                            
                            <div id="figureParams">
                                <!-- Параметры будут динамически добавлены здесь -->
                            </div>
                            
                            <div class="mb-3">
                                <label class="form-label">Цвет</label>
                                <input type="color" class="form-control" id="figureColor" value="#0000ff">
                            </div>
                        </div>
                        
                        <div class="col-md-6">
                            <div class="figure-preview">
                                <svg id="figurePreview" width="300" height="300" style="border: 1px solid #ddd;"></svg>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Отмена</button>
                    <button type="button" class="btn btn-primary" onclick="insertFigure()">Вставить</button>
                </div>
            </div>
        </div>
    </div>

    <style>
        .test-content {
            position: relative;
        }
        
        .figure-preview {
            background: #f8f9fa;
            padding: 20px;
            border-radius: 8px;
            margin-top: 20px;
        }
        
        .test-content textarea {
            font-family: 'Courier New', monospace;
            font-size: 14px;
            line-height: 1.5;
        }
        
        .card {
            border-radius: 15px;
            overflow: hidden;
        }
        
        .btn-group .btn {
            border-radius: 8px;
        }
    </style>

    <script>
        function addTheorySection() {
            const content = document.getElementById('content');
            content.value += '\n## Новый раздел теории\n\n';
            content.focus();
        }
        
        function addQuestion() {
            const content = document.getElementById('content');
            content.value += '\n== Новый вопрос ==\n[answer type="text" correct=""]\n';
            content.focus();
        }
        
        function showFigureModal() {
            const modal = new bootstrap.Modal(document.getElementById('figureModal'));
            modal.show();
            updateFigureParams();
        }
        
        function updateFigureParams() {
            const type = document.getElementById('figureType').value;
            const paramsDiv = document.getElementById('figureParams');
            let html = '';
            
            switch(type) {
                case 'circle':
                    html = `
                        <div class="mb-3">
                            <label class="form-label">Радиус</label>
                            <input type="number" class="form-control" id="radius" value="50" min="1">
                        </div>
                    `;
                    break;
                case 'triangle':
                    html = `
                        <div class="mb-3">
                            <label class="form-label">Сторона A</label>
                            <input type="number" class="form-control" id="sideA" value="60" min="1">
                        </div>
                        <div class="mb-3">
                            <label class="form-label">Сторона B</label>
                            <input type="number" class="form-control" id="sideB" value="80" min="1">
                        </div>
                        <div class="mb-3">
                            <label class="form-label">Сторона C</label>
                            <input type="number" class="form-control" id="sideC" value="100" min="1">
                        </div>
                    `;
                    break;
                case 'square':
                    html = `
                        <div class="mb-3">
                            <label class="form-label">Сторона</label>
                            <input type="number" class="form-control" id="side" value="80" min="1">
                        </div>
                    `;
                    break;
                case 'rectangle':
                    html = `
                        <div class="mb-3">
                            <label class="form-label">Длина</label>
                            <input type="number" class="form-control" id="length" value="100" min="1">
                        </div>
                        <div class="mb-3">
                            <label class="form-label">Ширина</label>
                            <input type="number" class="form-control" id="width" value="60" min="1">
                        </div>
                    `;
                    break;
                case 'polygon':
                    html = `
                        <div class="mb-3">
                            <label class="form-label">Количество сторон</label>
                            <input type="number" class="form-control" id="sides" value="5" min="3" max="12">
                        </div>
                        <div class="mb-3">
                            <label class="form-label">Радиус</label>
                            <input type="number" class="form-control" id="radius" value="50" min="1">
                        </div>
                    `;
                    break;
            }
            
            paramsDiv.innerHTML = html;
            updateFigurePreview();
        }
        
        function updateFigurePreview() {
            const type = document.getElementById('figureType').value;
            const color = document.getElementById('figureColor').value;
            const svg = document.getElementById('figurePreview');
            svg.innerHTML = '';
            
            const centerX = 150;
            const centerY = 150;
            
            switch(type) {
                case 'circle':
                    const radius = document.getElementById('radius').value;
                    svg.innerHTML = `
                        <circle cx="${centerX}" cy="${centerY}" r="${radius}" fill="none" stroke="${color}" stroke-width="2"/>
                        <line x1="${centerX}" y1="${centerY}" x2="${centerX + parseInt(radius)}" y2="${centerY}" stroke="red" stroke-width="1"/>
                        <text x="${centerX + parseInt(radius)/2}" y="${centerY - 10}" fill="red" font-size="12">r = ${radius}</text>
                    `;
                    break;
                    
                case 'triangle':
                    const a = parseInt(document.getElementById('sideA').value);
                    const b = parseInt(document.getElementById('sideB').value);
                    const c = parseInt(document.getElementById('sideC').value);
                    
                    // Простой треугольник для демонстрации
                    svg.innerHTML = `
                        <polygon points="50,180 150,180 100,50" fill="none" stroke="${color}" stroke-width="2"/>
                        <text x="50" y="190" font-size="12">a = ${a}</text>
                        <text x="150" y="190" font-size="12">b = ${b}</text>
                        <text x="100" y="40" font-size="12">c = ${c}</text>
                    `;
                    break;
                    
                case 'square':
                    const side = document.getElementById('side').value;
                    const squareX = centerX - side/2;
                    const squareY = centerY - side/2;
                    svg.innerHTML = `
                        <rect x="${squareX}" y="${squareY}" width="${side}" height="${side}" fill="none" stroke="${color}" stroke-width="2"/>
                        <text x="${centerX}" y="${centerY + parseInt(side)/2 + 20}" font-size="12">a = ${side}</text>
                    `;
                    break;
                    
                case 'rectangle':
                    const length = document.getElementById('length').value;
                    const width = document.getElementById('width').value;
                    const rectX = centerX - length/2;
                    const rectY = centerY - width/2;
                    svg.innerHTML = `
                        <rect x="${rectX}" y="${rectY}" width="${length}" height="${width}" fill="none" stroke="${color}" stroke-width="2"/>
                        <text x="${centerX}" y="${centerY + parseInt(width)/2 + 20}" font-size="12">a = ${length}</text>
                        <text x="${centerX - parseInt(length)/2 - 20}" y="${centerY}" font-size="12">b = ${width}</text>
                    `;
                    break;
                    
                case 'polygon':
                    const sides = parseInt(document.getElementById('sides').value);
                    const radius = document.getElementById('radius').value;
                    const points = [];
                    
                    for (let i = 0; i < sides; i++) {
                        const angle = (i * 2 * Math.PI / sides) - Math.PI / 2;
                        const x = centerX + radius * Math.cos(angle);
                        const y = centerY + radius * Math.sin(angle);
                        points.push(`${x},${y}`);
                    }
                    
                    svg.innerHTML = `
                        <polygon points="${points.join(' ')}" fill="none" stroke="${color}" stroke-width="2"/>
                        <text x="${centerX}" y="${centerY + parseInt(radius) + 20}" font-size="12">n = ${sides}</text>
                    `;
                    break;
            }
        }
        
        function insertFigure() {
            const type = document.getElementById('figureType').value;
            const color = document.getElementById('figureColor').value;
            let figureCode = '';
            
            switch(type) {
                case 'circle':
                    const radius = document.getElementById('radius').value;
                    figureCode = `<figure type="circle" radius="${radius}" color="${color}"/>`;
                    break;
                    
                case 'triangle':
                    const a = document.getElementById('sideA').value;
                    const b = document.getElementById('sideB').value;
                    const c = document.getElementById('sideC').value;
                    figureCode = `<figure type="triangle" sides="${a},${b},${c}" color="${color}"/>`;
                    break;
                    
                case 'square':
                    const side = document.getElementById('side').value;
                    figureCode = `<figure type="square" side="${side}" color="${color}"/>`;
                    break;
                    
                case 'rectangle':
                    const length = document.getElementById('length').value;
                    const width = document.getElementById('width').value;
                    figureCode = `<figure type="rectangle" length="${length}" width="${width}" color="${color}"/>`;
                    break;
                    
                case 'polygon':
                    const sides = document.getElementById('sides').value;
                    const polyRadius = document.getElementById('radius').value;
                    figureCode = `<figure type="polygon" sides="${sides}" radius="${polyRadius}" color="${color}"/>`;
                    break;
            }
            
            const content = document.getElementById('content');
            content.value += '\n' + figureCode + '\n';
            content.focus();
            
            const modal = bootstrap.Modal.getInstance(document.getElementById('figureModal'));
            modal.hide();
        }
        
        function previewTest() {
            const content = document.getElementById('content').value;
            // Здесь можно добавить логику предпросмотра
            alert('Функция предпросмотра будет добавлена позже');
        }
        
        // Инициализация
        document.getElementById('figureType').addEventListener('change', updateFigureParams);
        document.getElementById('figureColor').addEventListener('change', updateFigurePreview);
        document.getElementById('figureParams').addEventListener('change', updateFigurePreview);
    </script>
    {% endblock %}
    ''',
    
    'edit_test.html': '''
    {% extends "base.html" %}
    {% block title %}Редактировать тест{% endblock %}
    {% block content %}
        <h1>Редактировать тест: {{ test.title }}</h1>
        
        <form method="post">
            <div class="mb-3">
                <label for="title" class="form-label">Название теста</label>
                <input type="text" class="form-control" id="title" name="title" value="{{ test.title }}" required>
            </div>
            
            <div class="mb-3">
                <label for="subject" class="form-label">Предмет</label>
                <select class="form-select" id="subject" name="subject" required>
                    <option value="algebra" {% if test.subject == 'algebra' %}selected{% endif %}>Алгебра</option>
                    <option value="geometry" {% if test.subject == 'geometry' %}selected{% endif %}>Геометрия</option>
                    <option value="calculus" {% if test.subject == 'calculus' %}selected{% endif %}>Математический анализ</option>
                </select>
            </div>
            
            <div class="mb-3">
                <label for="xp_reward" class="form-label">Опыт за прохождение</label>
                <input type="number" class="form-control" id="xp_reward" name="xp_reward" value="{{ test.xp_reward }}" min="0">
            </div>
            
            <div class="mb-3">
                <label for="coin_reward" class="form-label">Монеты за прохождение</label>
                <input type="number" class="form-control" id="coin_reward" name="coin_reward" value="{{ test.coin_reward }}" min="0">
            </div>
            
            <div class="mb-3">
                <label for="title_reward" class="form-label">Титул за прохождение (необязательно)</label>
                <select class="form-select" id="title_reward" name="title_reward">
                    <option value="">Не выдавать титул</option>
                    {% for id, title in TITLES.items() %}
                        <option value="{{ id }}" {% if test.title_reward == id %}selected{% endif %}>{{ title.name }}</option>
                    {% endfor %}
                </select>
            </div>
            
            <div class="mb-3">
                <label for="content" class="form-label">Содержимое теста</label>
                <textarea class="form-control" id="content" name="content" rows="20" required>{{ test.content }}</textarea>
            </div>
            
            <button type="submit" class="btn btn-primary">Сохранить изменения</button>
        </form>
    {% endblock %}
    ''',

    'create_shop_item.html': '''
    {% extends "base.html" %}
    {% block title %}Добавить товар{% endblock %}
    {% block content %}
        <h1>Добавить товар в магазин</h1>
        
        <form method="post">
            <div class="mb-3">
                <label for="name" class="form-label">Название товара</label>
                <input type="text" class="form-control" id="name" name="name" required>
            </div>
            
            <div class="mb-3">
                <label for="description" class="form-label">Описание</label>
                <textarea class="form-control" id="description" name="description" rows="3"></textarea>
            </div>
            
            <div class="mb-3">
                <label for="price" class="form-label">Цена</label>
                <input type="number" class="form-control" id="price" name="price" min="1" value="10" required>
            </div>
            
            <div class="mb-3">
                <label for="item_type" class="form-label">Тип товара</label>
                <select class="form-select" id="item_type" name="item_type" required>
                    <option value="title">Титул</option>
                    <option value="badge">Значок</option>
                    <option value="background">Фон профиля</option>
                </select>
            </div>
            
            <div class="mb-3">
                <label for="image_url" class="form-label">URL изображения (необязательно)</label>
                <input type="text" class="form-control" id="image_url" name="image_url">
            </div>
            
            <button type="submit" class="btn btn-primary">Добавить товар</button>
        </form>
    {% endblock %}
    ''',
    
    'achievements.html': '''
    {% extends "base.html" %}
    {% block title %}Достижения{% endblock %}
    {% block content %}
        <h1>Достижения</h1>
        
        <div class="row">
            <div class="col-md-3">
                <div class="card mb-4">
                    <div class="card-body">
                        <h5 class="card-title">Статистика</h5>
                        <p class="card-text">
                            <strong>Уровень:</strong> {{ current_user.level }}<br>
                            <strong>Опыт:</strong> {{ current_user.xp }}<br>
                            <strong>Монеты:</strong> {{ current_user.coins }}<br>
                            <strong>Тестов пройдено:</strong> {{ current_user.progress|length }}
                        </p>
                    </div>
                </div>
            </div>
            
            <div class="col-md-9">
                {% for category, achievements in achievements_by_category.items() %}
                    {% if achievements %}
                        <div class="card mb-4">
                            <div class="card-header">
                                <h5 class="mb-0">
                                    {% if category == 'test_completed' %}
                                        За прохождение тестов
                                    {% elif category == 'perfect_score' %}
                                        За идеальные результаты
                                    {% elif category == 'streak' %}
                                        За серии
                                    {% else %}
                                        Прочие достижения
                                    {% endif %}
                                </h5>
                            </div>
                            <div class="card-body">
                                <div class="row">
                                    {% for item in achievements %}
                                        <div class="col-md-4 mb-3">
                                            <div class="achievement-card {% if item.user_progress %}unlocked{% else %}locked{% endif %}">
                                                <div class="achievement-icon">
                                                    {% if item.user_progress %}
                                                        <i class="fas fa-trophy text-warning"></i>
                                                    {% else %}
                                                        <i class="fas fa-lock text-secondary"></i>
                                                    {% endif %}
                                                </div>
                                                <div class="achievement-info">
                                                    <h6>{{ item.achievement.name }}</h6>
                                                    <p class="small">{{ item.achievement.description }}</p>
                                                    {% if item.user_progress %}
                                                        <span class="badge bg-success">Получено</span>
                                                    {% else %}
                                                        <div class="progress">
                                                            <div class="progress-bar" role="progressbar" 
                                                                 style="width: {{ (item.user_progress.progress / item.achievement.condition_value) * 100 }}%">
                                                                {{ item.user_progress.progress }}/{{ item.achievement.condition_value }}
                                                            </div>
                                                        </div>
                                                    {% endif %}
                                                </div>
                                            </div>
                                        </div>
                                    {% endfor %}
                                </div>
                            </div>
                        </div>
                    {% endif %}
                {% endfor %}
            </div>
        </div>
        
        <style>
            .achievement-card {
                border: 1px solid #ddd;
                border-radius: 8px;
                padding: 15px;
                height: 100%;
                display: flex;
                align-items: center;
                background: #f8f9fa;
            }
            
            .achievement-card.unlocked {
                background: #fff;
                border-color: #ffc107;
            }
            
            .achievement-icon {
                font-size: 2rem;
                margin-right: 15px;
            }
            
            .achievement-info {
                flex: 1;
            }
            
            .progress {
                height: 5px;
                margin-top: 5px;
            }
        </style>
    {% endblock %}
    ''',
    
    'daily_tasks.html': '''
    {% extends "base.html" %}
    {% block title %}Ежедневные задания{% endblock %}
    {% block content %}
        <h1>Ежедневные задания</h1>
        
        <div class="row">
            <div class="col-md-3">
                <div class="card mb-4">
                    <div class="card-body">
                        <h5 class="card-title">Статистика</h5>
                        <p class="card-text">
                            <strong>Уровень:</strong> {{ current_user.level }}<br>
                            <strong>Опыт:</strong> {{ current_user.xp }}<br>
                            <strong>Монеты:</strong> {{ current_user.coins }}
                        </p>
                    </div>
                </div>
            </div>
            
            <div class="col-md-9">
                <div class="card">
                    <div class="card-body">
                        <h5 class="card-title">Активные задания</h5>
                        {% for task in active_tasks %}
                            {% set user_task = user_tasks|selectattr('task_id', 'equalto', task.id)|first %}
                            <div class="task-card mb-3 {% if user_task and user_task.completed_at %}completed{% endif %}">
                                <div class="d-flex justify-content-between align-items-center">
                                    <div>
                                        <h6>{{ task.title }}</h6>
                                        <p class="small mb-0">{{ task.description }}</p>
                                    </div>
                                    <div class="text-end">
                                        <div class="reward">
                                            <span class="badge bg-primary">+{{ task.xp_reward }} XP</span>
                                            <span class="badge bg-warning">+{{ task.coin_reward }} монет</span>
                                        </div>
                                        {% if user_task and user_task.completed_at %}
                                            <span class="badge bg-success">Выполнено</span>
                                        {% else %}
                                            <div class="progress" style="width: 200px;">
                                                <div class="progress-bar" role="progressbar" 
                                                     style="width: {{ (user_task.progress / task.task_value) * 100 }}%">
                                                    {{ user_task.progress }}/{{ task.task_value }}
                                                </div>
                                            </div>
                                        {% endif %}
                                    </div>
                                </div>
                            </div>
                        {% endfor %}
                    </div>
                </div>
            </div>
        </div>
        
        <style>
            .task-card {
                border: 1px solid #ddd;
                border-radius: 8px;
                padding: 15px;
                background: #f8f9fa;
            }
            
            .task-card.completed {
                background: #fff;
                border-color: #28a745;
            }
            
            .reward {
                margin-bottom: 5px;
            }
            
            .progress {
                height: 5px;
            }
        </style>
    {% endblock %}
    ''',
    
    'friends.html': '''
    {% extends "base.html" %}
    {% block title %}Друзья{% endblock %}
    {% block content %}
        <h1>Друзья</h1>
        
        <div class="row">
            <div class="col-md-4">
                <div class="card mb-4">
                    <div class="card-body">
                        <h5 class="card-title">Запросы в друзья</h5>
                        {% if requests %}
                            {% for user in requests %}
                                <div class="friend-request mb-2">
                                    <div class="d-flex justify-content-between align-items-center">
                                        <span>{{ user.username }}</span>
                                        <form method="post" action="{{ url_for('accept_friend', user_id=user.id) }}" style="display: inline;">
                                            <button type="submit" class="btn btn-sm btn-success">Принять</button>
                                        </form>
                                    </div>
                                </div>
                            {% endfor %}
                        {% else %}
                            <p class="text-muted">Нет новых запросов</p>
                        {% endif %}
                    </div>
                </div>
            </div>
            
            <div class="col-md-8">
                <div class="card">
                    <div class="card-body">
                        <h5 class="card-title">Мои друзья</h5>
                        {% if friends %}
                            <div class="row">
                                {% for user in friends %}
                                    <div class="col-md-6 mb-3">
                                        <div class="friend-card">
                                            <div class="d-flex align-items-center">
                                                <div class="friend-avatar">
                                                    <i class="fas fa-user"></i>
                                                </div>
                                                <div class="friend-info ms-3">
                                                    <h6 class="mb-0">{{ user.username }}</h6>
                                                    <small class="text-muted">Уровень {{ user.level }}</small>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                {% endfor %}
                            </div>
                        {% else %}
                            <p class="text-muted">У вас пока нет друзей</p>
                        {% endif %}
                    </div>
                </div>
            </div>
        </div>
        
        <style>
            .friend-request {
                padding: 10px;
                border: 1px solid #ddd;
                border-radius: 4px;
                background: #f8f9fa;
            }
            
            .friend-card {
                padding: 15px;
                border: 1px solid #ddd;
                border-radius: 8px;
                background: #f8f9fa;
            }
            
            .friend-avatar {
                width: 40px;
                height: 40px;
                border-radius: 50%;
                background: #e9ecef;
                display: flex;
                align-items: center;
                justify-content: center;
            }
        </style>
    {% endblock %}
    ''',
    
    'leaderboard.html': '''
    {% extends "base.html" %}
    {% block title %}Рейтинг{% endblock %}
    {% block content %}
        <h1>Рейтинг игроков</h1>
        
        <div class="row">
            <div class="col-md-4">
                <div class="card mb-4">
                    <div class="card-header">
                        <h5 class="mb-0">Топ по опыту</h5>
                    </div>
                    <div class="card-body">
                        <div class="list-group">
                            {% for user in top_users %}
                                <div class="list-group-item">
                                    <div class="d-flex justify-content-between align-items-center">
                                        <div>
                                            <h6 class="mb-0">{{ user.username }}</h6>
                                            <small class="text-muted">Уровень {{ user.level }}</small>
                                        </div>
                                        <span class="badge bg-primary">{{ user.xp }} XP</span>
                                    </div>
                                </div>
                            {% endfor %}
                        </div>
                    </div>
                </div>
            </div>
            
            <div class="col-md-4">
                <div class="card mb-4">
                    <div class="card-header">
                        <h5 class="mb-0">Топ по уровню</h5>
                    </div>
                    <div class="card-body">
                        <div class="list-group">
                            {% for user in top_levels %}
                                <div class="list-group-item">
                                    <div class="d-flex justify-content-between align-items-center">
                                        <div>
                                            <h6 class="mb-0">{{ user.username }}</h6>
                                            <small class="text-muted">{{ user.xp }} XP</small>
                                        </div>
                                        <span class="badge bg-success">Уровень {{ user.level }}</span>
                                    </div>
                                </div>
                            {% endfor %}
                        </div>
                    </div>
                </div>
            </div>
            
            <div class="col-md-4">
                <div class="card mb-4">
                    <div class="card-header">
                        <h5 class="mb-0">Топ по монетам</h5>
                    </div>
                    <div class="card-body">
                        <div class="list-group">
                            {% for user in top_coins %}
                                <div class="list-group-item">
                                    <div class="d-flex justify-content-between align-items-center">
                                        <div>
                                            <h6 class="mb-0">{{ user.username }}</h6>
                                            <small class="text-muted">Уровень {{ user.level }}</small>
                                        </div>
                                        <span class="badge bg-warning">{{ user.coins }} монет</span>
                                    </div>
                                </div>
                            {% endfor %}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    {% endblock %}
    '''
}

app.jinja_loader = DictLoader(TEMPLATES)

# Маршруты
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')

        if not username or not email or not password:
            flash('Пожалуйста, заполните все поля.', 'warning')
            return render_template('register.html')

        if User.query.filter_by(username=username).first():
            flash('Имя пользователя уже занято.', 'danger')
        elif User.query.filter_by(email=email).first():
            flash('Email уже используется.', 'danger')
        else:
            new_user = User(
                username=username,
                email=email,
                created_at=datetime.utcnow()
            )
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()

            flash('Регистрация прошла успешно!', 'success')
            return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            session['user_id'] = user.id
            flash('Вход выполнен успешно!', 'success')
            return redirect(url_for('profile'))
        else:
            flash('Неверное имя пользователя или пароль.', 'danger')

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('Вы успешно вышли из системы', 'info')
    return redirect(url_for('index'))

@app.route('/profile')
@login_required
def profile():
    user = get_current_user()
    progress = UserProgress.query.filter_by(user_id=user.id).join(Test).all()
    titles = json.loads(user.titles)
    user_titles = [{"id": tid, **TITLES.get(tid, {"name": f"Титул {tid}", "description": "Неизвестный титул"})} for tid in titles]
    
    return render_template('profile.html', 
                         current_user=user, 
                         progress=progress,
                         user_titles=user_titles)

@app.route('/equip_title/<int:title_id>', methods=['POST'])
@login_required
def equip_title(title_id):
    user = get_current_user()
    titles = json.loads(user.titles)
    
    if title_id in titles:
        user.equipped_title = title_id
        db.session.commit()
        flash(f"Титул '{TITLES.get(title_id, {}).get('name', '')}' теперь отображается в вашем профиле", "success")
    else:
        flash("У вас нет этого титула", "danger")
    
    return redirect(url_for('profile'))

@app.route('/shop')
@login_required
def shop():
    items = ShopItem.query.all()
    return render_template('shop.html', items=items)

@app.route('/buy/<int:item_id>', methods=['POST'])
@login_required
def buy_item(item_id):
    user = get_current_user()
    item = ShopItem.query.get_or_404(item_id)
    
    if user.coins >= item.price:
        if item.item_type == 'title':
            if user.add_title(item.id):
                user.add_coins(-item.price)
                flash(f"Вы успешно приобрели титул '{item.name}'!", "success")
            else:
                flash("У вас уже есть этот титул", "warning")
        else:
            if user.add_item(item.id):
                user.add_coins(-item.price)
                flash(f"Вы успешно приобрели '{item.name}'!", "success")
            else:
                flash("У вас уже есть этот предмет", "warning")
    else:
        flash("Недостаточно монет для покупки", "danger")
    
    return redirect(url_for('shop'))

@app.route('/tests')
def tests():
    subject = request.args.get('subject')
    tests_query = Test.query.filter_by(subject=subject) if subject else Test.query
    tests = tests_query.all()
    return render_template('tests.html', tests=tests, subject=subject)

@app.route('/test/<int:test_id>', methods=['GET', 'POST'])
@login_required
def test(test_id):
    test = Test.query.get_or_404(test_id)
    user = get_current_user()
    
    if request.method == 'POST':
        user_answers = {}
        for key, value in request.form.lists():
            if key.startswith('q'):
                q_id = key[1:]  # Извлекаем номер вопроса
                user_answers[q_id] = value[0] if len(value) == 1 else value

        score, results = calculate_score(user_answers, test.questions)

        # Проверяем, не проходил ли пользователь уже этот тест
        existing_progress = UserProgress.query.filter_by(user_id=user.id, test_id=test.id).first()
        
        if not existing_progress:
            # Награждаем только при первом прохождении
            progress = UserProgress(
                user_id=user.id,
                test_id=test.id,
                score=score,
                completed_at=datetime.utcnow()
            )
            db.session.add(progress)
            
            # Выдаем награды
            user.add_xp(test.xp_reward)
            user.add_coins(test.coin_reward)
            
            title_reward = None
            if test.title_reward:
                if user.add_title(test.title_reward):
                    title_reward = test.title_reward
                    flash(f"Вы получили новый титул: {TITLES.get(test.title_reward, {}).get('name', '')}!", "success")
            
            db.session.commit()
        else:
            # Обновляем результат, но не награждаем
            existing_progress.score = score
            existing_progress.completed_at = datetime.utcnow()
            title_reward = None
            db.session.commit()

        return render_template('test_result.html', 
                            test=test, 
                            score=score, 
                            results=results,
                            xp_reward=0 if existing_progress else test.xp_reward,
                            coin_reward=0 if existing_progress else test.coin_reward,
                            title_reward=title_reward)

    # Парсим контент теста
    parser = TestLanguageParser(test.content)
    return render_template('test.html', test=test, parsed={
        'title': parser.metadata['title'],
        'description': parser.metadata.get('description', ''),
        'rules': parser.rules,
        'figures': [render_figure(fig) for fig in parser.rules if isinstance(fig, dict)],
        'questions': parser.questions
    })

@app.route('/calculator')
def calculator():
    return render_template('calculator.html')

@app.route('/api/calculate', methods=['POST'])
def api_calculate():
    data = request.get_json()
    try:
        # Безопасное вычисление
        result = eval(data['expression'], {'__builtins__': None}, {
            'sin': math.sin,
            'cos': math.cos,
            'tan': math.tan,
            'sqrt': math.sqrt,
            'pi': math.pi,
            'log': math.log,
            'exp': math.exp
        })
        return jsonify({'result': result})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

# Админ-маршруты
@app.route('/admin')
@admin_required
def admin_panel():
    users = User.query.order_by(User.created_at.desc()).all()
    tests = Test.query.order_by(Test.id.desc()).all()
    shop_items = ShopItem.query.all()
    return render_template('admin.html', users=users, tests=tests, shop_items=shop_items)

@app.route('/admin/create_test', methods=['GET', 'POST'])
@admin_required
def create_test():
    if request.method == 'POST':
        try:
            title = request.form['title']
            subject = request.form['subject']
            xp_reward = int(request.form['xp_reward'])
            coin_reward = int(request.form['coin_reward'])
            title_reward = request.form['title_reward']
            content = request.form['content']

            # Validate inputs
            if not title or len(title) > 200:
                raise ValueError("Title must be between 1 and 200 characters")
            if subject not in ['algebra', 'geometry', 'calculus']:
                raise ValueError("Invalid subject")
            if xp_reward < 0 or coin_reward < 0:
                raise ValueError("Rewards cannot be negative")
            if title_reward and int(title_reward) not in TITLES:
                raise ValueError("Invalid title reward ID")
            
            # Validate test content
            parser = TestLanguageParser(content)
            
            test = Test(
                title=title,
                subject=subject,
                xp_reward=xp_reward,
                coin_reward=coin_reward,
                title_reward=int(title_reward) if title_reward else None,
                content=content
            )
            
            db.session.add(test)
            db.session.commit()
            
            # Save questions
            for question in parser.questions:
                q = Question(
                    test_id=test.id,
                    text=question['text'],
                    answer_type=question['answer_type'],
                    options=json.dumps(question['options']) if question.get('options') else None,
                    correct_answer=json.dumps(question['correct_answer']),
                    figure_data=json.dumps(question.get('figure')) if question.get('figure') else None
                )
                db.session.add(q)
            
            db.session.commit()
            flash('Тест успешно создан!', 'success')
            return redirect(url_for('admin_panel'))
            
        except ValueError as e:
            flash(f'Ошибка при создании теста: {str(e)}', 'danger')
        except Exception as e:
            flash(f'Неизвестная ошибка: {str(e)}', 'danger')
    
    return render_template('create_test.html')

@app.route('/admin/edit_test/<int:test_id>', methods=['GET', 'POST'])
@admin_required
def edit_test(test_id):
    test = Test.query.get_or_404(test_id)
    
    if request.method == 'POST':
        try:
            title = request.form['title']
            subject = request.form['subject']
            xp_reward = int(request.form['xp_reward'])
            coin_reward = int(request.form['coin_reward'])
            title_reward = request.form['title_reward']
            content = request.form['content']

            # Validate inputs
            if not title or len(title) > 200:
                raise ValueError("Title must be between 1 and 200 characters")
            if subject not in ['algebra', 'geometry', 'calculus']:
                raise ValueError("Invalid subject")
            if xp_reward < 0 or coin_reward < 0:
                raise ValueError("Rewards cannot be negative")
            if title_reward and int(title_reward) not in TITLES:
                raise ValueError("Invalid title reward ID")
            
            # Validate test content
            parser = TestLanguageParser(content)
            
            test.title = title
            test.subject = subject
            test.xp_reward = xp_reward
            test.coin_reward = coin_reward
            test.title_reward = int(title_reward) if title_reward else None
            test.content = content
            
            # Delete old questions
            Question.query.filter_by(test_id=test.id).delete()
            
            # Add new questions
            for question in parser.questions:
                q = Question(
                    test_id=test.id,
                    text=question['text'],
                    answer_type=question['answer_type'],
                    options=json.dumps(question['options']) if question.get('options') else None,
                    correct_answer=json.dumps(question['correct_answer']),
                    figure_data=json.dumps(question.get('figure')) if question.get('figure') else None
                )
                db.session.add(q)
            
            db.session.commit()
            flash('Тест успешно обновлен!', 'success')
            return redirect(url_for('admin_panel'))
            
        except ValueError as e:
            flash(f'Ошибка при обновлении теста: {str(e)}', 'danger')
        except Exception as e:
            flash(f'Неизвестная ошибка: {str(e)}', 'danger')
    
    return render_template('edit_test.html', test=test)

@app.route('/admin/delete_test/<int:test_id>', methods=['POST'])
@admin_required
def delete_test(test_id):
    test = Test.query.get_or_404(test_id)
    db.session.delete(test)
    db.session.commit()
    flash('Тест успешно удален!', 'success')
    return redirect(url_for('admin_panel'))

@app.route('/admin/toggle_admin/<int:user_id>', methods=['POST'])
@admin_required
def toggle_admin(user_id):
    user = User.query.get_or_404(user_id)
    user.is_admin = not user.is_admin
    db.session.commit()
    flash(f'Права администратора для {user.username} {"выданы" if user.is_admin else "отозваны"}', 'success')
    return redirect(url_for('admin_panel'))

@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    flash(f'Пользователь {user.username} удален', 'success')
    return redirect(url_for('admin_panel'))

@app.route('/admin/reset_password/<int:user_id>', methods=['POST'])
@admin_required
def reset_password(user_id):
    user = User.query.get_or_404(user_id)
    new_password = '123456'  # Простой пароль для сброса
    user.set_password(new_password)
    db.session.commit()
    flash(f'Пароль для {user.username} сброшен на "123456"', 'success')
    return redirect(url_for('admin_panel'))

@app.route('/admin/create_shop_item', methods=['GET', 'POST'])
@admin_required
def create_shop_item():
    if request.method == 'POST':
        try:
            name = request.form['name']
            description = request.form['description']
            price = int(request.form['price'])
            item_type = request.form['item_type']
            image_url = request.form.get('image_url', '')

            # Validate inputs
            if not name or len(name) > 100:
                raise ValueError("Name must be between 1 and 100 characters")
            if price < 1:
                raise ValueError("Price must be at least 1 coin")
            if item_type not in ['title', 'badge', 'background']:
                raise ValueError("Invalid item type")
            if image_url and not image_url.startswith(('http://', 'https://', '/')):
                raise ValueError("Invalid image URL format")

            item = ShopItem(
                name=name,
                description=description,
                price=price,
                item_type=item_type,
                image_url=image_url
            )
            
            db.session.add(item)
            db.session.commit()
            flash('Товар успешно добавлен в магазин!', 'success')
            return redirect(url_for('admin_panel'))
            
        except ValueError as e:
            flash(f'Ошибка при создании товара: {str(e)}', 'danger')
        except Exception as e:
            flash(f'Неизвестная ошибка: {str(e)}', 'danger')
    
    return render_template('create_shop_item.html')

@app.route('/admin/delete_shop_item/<int:item_id>', methods=['POST'])
@admin_required
def delete_shop_item(item_id):
    item = ShopItem.query.get_or_404(item_id)
    db.session.delete(item)
    db.session.commit()
    flash('Товар успешно удален из магазина!', 'success')
    return redirect(url_for('admin_panel'))

# Инициализация базы данных
def init_db():
    with app.app_context():
        db.create_all()

        if not User.query.first():
            # Создаем администратора
            admin = User(
            username='admin',
            email='admin@math.ru',
            is_admin=True,
            xp=1000,
            level=10,
            coins=500,
            titles=json.dumps(list(range(1, 11)))  # Первые 10 титулов
)# Первые 10 титулов
            admin.set_password('admin123')
            db.session.add(admin)

            # Создаем тестового пользователя
            user = User(
                username='user',
                email='user@math.ru',
                xp=250,
                level=3,
                coins=100,
                titles=json.dumps([1, 2, 4]))  # Новичок, Математик, Геометр
            user.set_password('user123')
            db.session.add(user)

            # Пример теста по геометрии
            geometry_test_content = """
@test: Геометрические фигуры
@subject: geometry
@description: Тест по вычислению площадей и периметров
@xp_reward: 20
@coin_reward: 15
@title_reward: 4

## Формула площади круга: S = π × r²
<figure type="circle" radius="5" />

== Чему равна площадь круга с радиусом 5? ==
[answer type="number" correct="78.53981633974483"]

== Чему равна длина окружности с радиусом 5? ==
[answer type="number" correct="31.41592653589793"]

## Формула Герона: S = √[p(p-a)(p-b)(p-c)], где p = (a+b+c)/2
<figure type="triangle" sides="3,4,5" />

== Чему равна площадь треугольника со сторонами 3, 4, 5? ==
[answer type="number" correct="6"]

== Чему равен периметр этого треугольника? ==
[answer type="number" correct="12"]
"""

            geometry_test = Test(
                title="Геометрические фигуры",
                subject="geometry",
                description="Тест по вычислению площадей и периметров",
                content=geometry_test_content,
                xp_reward=20,
                coin_reward=15,
                title_reward=4  # Титул "Геометр"
            )
            db.session.add(geometry_test)

            # Пример теста по алгебре
            algebra_test_content = """
@test: Алгебраические выражения
@subject: algebra
@description: Тест по решению уравнений
@xp_reward: 15
@coin_reward: 10
@title_reward: 5

## Решение линейных уравнений
Линейное уравнение имеет вид: ax + b = 0

== Решите уравнение: 2x + 5 = 0 ==
[answer type="number" correct="-2.5"]

== Решите уравнение: 3x - 6 = 0 ==
[answer type="number" correct="2"]

## Квадратные уравнения
Квадратное уравнение имеет вид: ax² + bx + c = 0

== Решите уравнение: x² - 4 = 0 ==
[answer type="multiple_choice" options="2|-2|2 и -2|Нет решений" correct="2 и -2"]
"""

            algebra_test = Test(
                title="Алгебраические выражения",
                subject="algebra",
                description="Тест по решению уравнений",
                content=algebra_test_content,
                xp_reward=15,
                coin_reward=10,
                title_reward=5  # Титул "Алгебраист"
            )
            db.session.add(algebra_test)

            # Добавляем товары в магазин
            shop_items = [
                ShopItem(
                    name="Титул 'Математик'",
                    description="Показывает ваши знания в математике",
                    price=50,
                    item_type="title"
                ),
                ShopItem(
                    name="Титул 'Гений'",
                    description="Для настоящих знатоков математики",
                    price=100,
                    item_type="title"
                ),
                ShopItem(
                    name="Золотая рамка",
                    description="Стильное оформление профиля",
                    price=75,
                    item_type="badge",
                    image_url="/static/gold_frame.png"
                ),
                ShopItem(
                    name="Фон 'Космос'",
                    description="Красивый космический фон для профиля",
                    price=120,
                    item_type="background",
                    image_url="/static/space_bg.jpg"
                )
            ]
            db.session.add_all(shop_items)

            # Добавляем прогресс для тестового пользователя
            progress = [
                UserProgress(
                    user_id=user.id,
                    test_id=geometry_test.id,
                    score=85.0,
                    completed_at=datetime.utcnow()
                ),
                UserProgress(
                    user_id=user.id,
                    test_id=algebra_test.id,
                    score=90.0,
                    completed_at=datetime.utcnow()
                )
            ]
            db.session.add_all(progress)

            db.session.commit()

class SimpleTestParser:
    def __init__(self, content):
        if not content or not isinstance(content, str):
            raise ValueError("Test content must be a non-empty string")
        self.content = content
        self.metadata = {
            'title': 'Без названия',
            'subject': 'general',
            'description': '',
            'xp_reward': 10,
            'coin_reward': 5,
            'title_reward': None
        }
        self.sections = []
        self.questions = []
        self.parse()

    def parse(self):
        try:
            lines = self.content.split('\n')
            current_section = None
            current_question = None

            for line in lines:
                line = line.strip()
                if not line:
                    continue

                # Метаданные
                if line.startswith('#'):
                    if line.startswith('#title:'):
                        self.metadata['title'] = line[7:].strip()
                    elif line.startswith('#subject:'):
                        subject = line[9:].strip()
                        if subject not in ['algebra', 'geometry', 'calculus']:
                            raise ValueError(f"Invalid subject: {subject}")
                        self.metadata['subject'] = subject
                    elif line.startswith('#description:'):
                        self.metadata['description'] = line[13:].strip()
                    elif line.startswith('#xp:'):
                        try:
                            self.metadata['xp_reward'] = int(line[4:].strip())
                        except ValueError:
                            raise ValueError("XP reward must be an integer")
                    elif line.startswith('#coins:'):
                        try:
                            self.metadata['coin_reward'] = int(line[7:].strip())
                        except ValueError:
                            raise ValueError("Coin reward must be an integer")
                    elif line.startswith('#title_reward:'):
                        try:
                            title_id = line[14:].strip()
                            self.metadata['title_reward'] = int(title_id) if title_id else None
                        except ValueError:
                            raise ValueError("Title reward must be an integer")
                    continue

                # Разделы теории
                if line.startswith('##'):
                    current_section = {
                        'type': 'theory',
                        'title': line[2:].strip(),
                        'content': ''
                    }
                    self.sections.append(current_section)
                    continue

                # Фигуры
                if line.startswith('@figure'):
                    figure_type = re.search(r'type="([^"]+)"', line)
                    if not figure_type:
                        raise ValueError("Figure must have a type")
                    
                    figure_data = self.parse_figure(line)
                    if figure_data:
                        if current_section and current_section['type'] == 'theory':
                            current_section['content'] += "\n" + str(figure_data)
                        else:
                            self.sections.append({'type': 'figure', 'data': figure_data})
                    continue

                # Вопросы
                if line.startswith('?'):
                    if current_question:
                        self.questions.append(current_question)
                    
                    current_question = {
                        'text': line[1:].strip(),
                        'type': None,
                        'options': None,
                        'answer': None,
                        'hint': None,
                        'explanation': None
                    }
                    continue

                # Ответы и подсказки
                if current_question:
                    if line.startswith('+'):
                        current_question['answer'] = line[1:].strip()
                    elif line.startswith('*'):
                        current_question['hint'] = line[1:].strip()
                    elif line.startswith('!'):
                        current_question['explanation'] = line[1:].strip()
                    elif line.startswith('-'):
                        if not current_question['options']:
                            current_question['options'] = []
                        current_question['options'].append(line[1:].strip())
                        current_question['type'] = 'multiple_choice'
                    else:
                        current_question['type'] = 'text' if not current_question['type'] else current_question['type']

                # Теоретический контент
                elif current_section:
                    current_section['content'] += "\n" + line

            # Добавляем последний вопрос
            if current_question:
                self.questions.append(current_question)

            # Валидация
            if not self.questions:
                raise ValueError("Test must have at least one question")
            
            for i, q in enumerate(self.questions, 1):
                if not q.get('answer'):
                    raise ValueError(f"Question {i} is missing an answer")
                if q.get('type') == 'multiple_choice' and not q.get('options'):
                    raise ValueError(f"Question {i} is missing options")

        except Exception as e:
            raise ValueError(f"Error parsing test content: {str(e)}")

    def parse_figure(self, line):
        try:
            figure_type = re.search(r'type="([^"]+)"', line).group(1)
            params = {}

            if figure_type == 'circle':
                radius = float(re.search(r'radius="([^"]+)"', line).group(1))
                params = {'radius': radius}
                area = math.pi * radius ** 2
                circumference = 2 * math.pi * radius
                return {
                    'type': 'figure',
                    'figure': 'circle',
                    'params': params,
                    'formulas': [
                        f'Площадь: S = π × r² = {area:.2f}',
                        f'Длина окружности: C = 2πr = {circumference:.2f}'
                    ]
                }

            elif figure_type == 'triangle':
                sides = re.search(r'sides="([^"]+)"', line).group(1).split(',')
                a, b, c = map(float, sides)
                params = {'a': a, 'b': b, 'c': c}
                s = (a + b + c) / 2
                area = math.sqrt(s * (s - a) * (s - b) * (s - c))
                return {
                    'type': 'figure',
                    'figure': 'triangle',
                    'params': params,
                    'formulas': [
                        f'Площадь (Герон): S = √[p(p-a)(p-b)(p-c)] = {area:.2f}',
                        f'Периметр: P = a + b + c = {a + b + c}'
                    ]
                }

            elif figure_type == 'square':
                side = float(re.search(r'side="([^"]+)"', line).group(1))
                params = {'side': side}
                area = side ** 2
                perimeter = 4 * side
                return {
                    'type': 'figure',
                    'figure': 'square',
                    'params': params,
                    'formulas': [
                        f'Площадь: S = a² = {area}',
                        f'Периметр: P = 4a = {perimeter}'
                    ]
                }

            elif figure_type == 'rectangle':
                length = float(re.search(r'length="([^"]+)"', line).group(1))
                width = float(re.search(r'width="([^"]+)"', line).group(1))
                params = {'length': length, 'width': width}
                area = length * width
                perimeter = 2 * (length + width)
                return {
                    'type': 'figure',
                    'figure': 'rectangle',
                    'params': params,
                    'formulas': [
                        f'Площадь: S = a × b = {area}',
                        f'Периметр: P = 2(a + b) = {perimeter}'
                    ]
                }

        except Exception as e:
            print(f"Ошибка при разборе фигуры: {e}")
            return None

@app.route('/achievements')
@login_required
def achievements():
    user = get_current_user()
    user_achievements = UserAchievement.query.filter_by(user_id=user.id).all()
    all_achievements = Achievement.query.all()
    
    # Группируем достижения по категориям
    achievements_by_category = {
        'test_completed': [],
        'perfect_score': [],
        'streak': [],
        'other': []
    }
    
    for achievement in all_achievements:
        user_achievement = next((ua for ua in user_achievements if ua.achievement_id == achievement.id), None)
        category = achievement.condition_type.split('_')[0] if achievement.condition_type else 'other'
        achievements_by_category[category].append({
            'achievement': achievement,
            'user_progress': user_achievement
        })
    
    return render_template('achievements.html', 
                         achievements_by_category=achievements_by_category,
                         current_user=user)

@app.route('/daily_tasks')
@login_required
def daily_tasks():
    user = get_current_user()
    today = datetime.utcnow().date()
    
    # Получаем активные задания
    active_tasks = DailyTask.query.filter_by(active=True).all()
    user_tasks = UserDailyTask.query.filter_by(user_id=user.id).all()
    
    # Обновляем прогресс
    for task in active_tasks:
        user_task = next((ut for ut in user_tasks if ut.task_id == task.id), None)
        if not user_task:
            user_task = UserDailyTask(user_id=user.id, task_id=task.id)
            db.session.add(user_task)
        
        # Проверяем прогресс
        if task.task_type == 'complete_test':
            progress = UserProgress.query.filter_by(user_id=user.id).count()
        elif task.task_type == 'get_perfect_score':
            progress = UserProgress.query.filter_by(user_id=user.id, score=100).count()
        elif task.task_type == 'earn_xp':
            progress = user.xp
        else:
            progress = 0
        
        user_task.progress = progress
        if progress >= task.task_value and not user_task.completed_at:
            user_task.completed_at = datetime.utcnow()
            user.add_xp(task.xp_reward)
            user.add_coins(task.coin_reward)
            flash(f'Задание выполнено! Получено {task.xp_reward} XP и {task.coin_reward} монет.', 'success')
    
    db.session.commit()
    
    # Обновляем список заданий
    user_tasks = UserDailyTask.query.filter_by(user_id=user.id).all()
    
    return render_template('daily_tasks.html',
                         active_tasks=active_tasks,
                         user_tasks=user_tasks,
                         current_user=user)

@app.route('/friends')
@login_required
def friends():
    user = get_current_user()
    
    try:
        friend_ids = json.loads(user.friends)
        request_ids = json.loads(user.friend_requests)
    except json.JSONDecodeError:
        friend_ids = []
        request_ids = []
    
    friends = User.query.filter(User.id.in_(friend_ids)).all()
    requests = User.query.filter(User.id.in_(request_ids)).all()
    
    return render_template('friends.html',
                         friends=friends,
                         requests=requests,
                         current_user=user)

@app.route('/add_friend/<int:user_id>', methods=['POST'])
@login_required
def add_friend(user_id):
    user = get_current_user()
    friend = User.query.get_or_404(user_id)
    
    if friend.add_friend_request(user.id):
        flash(f'Запрос в друзья отправлен пользователю {friend.username}', 'success')
    else:
        flash('Запрос уже был отправлен ранее', 'warning')
    
    return redirect(url_for('friends'))

@app.route('/accept_friend/<int:user_id>', methods=['POST'])
@login_required
def accept_friend(user_id):
    user = get_current_user()
    friend = User.query.get_or_404(user_id)
    
    try:
        requests = json.loads(user.friend_requests)
        if user_id in requests:
            requests.remove(user_id)
            user.friend_requests = json.dumps(requests)
            user.add_friend(user_id)
            friend.add_friend(user.id)
            flash(f'Вы теперь друзья с {friend.username}', 'success')
        else:
            flash('Запрос в друзья не найден', 'warning')
    except json.JSONDecodeError:
        flash('Ошибка при обработке запроса', 'danger')
    
    return redirect(url_for('friends'))

@app.route('/leaderboard')
def leaderboard():
    # Получаем топ-10 пользователей по XP
    top_users = User.query.order_by(User.xp.desc()).limit(10).all()
    
    # Получаем топ-10 пользователей по уровню
    top_levels = User.query.order_by(User.level.desc(), User.xp.desc()).limit(10).all()
    
    # Получаем топ-10 пользователей по монетам
    top_coins = User.query.order_by(User.coins.desc()).limit(10).all()
    
    return render_template('leaderboard.html',
                         top_users=top_users,
                         top_levels=top_levels,
                         top_coins=top_coins)

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)