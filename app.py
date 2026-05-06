#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
基于 Flask + SQLAlchemy + requests 的个人博客
- 文章列表、详情（Markdown → HTML）
- 管理后台（需要登录）
- 使用 requests 获取外部名言 API 示例
"""

import os
import hashlib
import mimetypes
from functools import wraps
from datetime import datetime
from werkzeug.utils import secure_filename
from flask import Flask, render_template, request, redirect, url_for, session, abort, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
import markdown
import requests

# ------------------------------- 配置 ----------------------------
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key')
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'blog.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(basedir, 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024
ALLOWED_EXTENSIONS = {
    'image' : {'png', 'jpg', 'jpeg', 'gif', 'webp'},
    'audio' : {'mp3', 'wav', 'ogg', 'm4a'},
    'video' : {'mp4', 'webm', 'avi', 'mov', 'mkv'}
}

for sub in ['images', 'audios', 'videos'] :
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], sub), exist_ok=True)

db = SQLAlchemy(app)

# 管理员密码
ADMIN_PASSWORD_HASH = hashlib.sha256('password'.encode()).hexdigest()

# ----------------------------- 数据库模型 -----------------------------
class Article(db.Model) :
    __tablename__ = 'article'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content_md = db.Column(db.Text, nullable=False)   # 存储 Markdown 原文
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, default=db.func.current_timestamp(), onupdate=db.func.current_timestamp())

    media_records = db.relationship('Media_Record', backref='article', lazy=True, cascade="all, delete-orphan")

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'content_md': self.content_md,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S')
        }

    def render_html(self):
        """将 Markdown 转为 HTML"""
        return markdown.markdown(self.content_md, extensions=['extra', 'codehilite'])
    
class Media_Record(db.Model) :
    __tablename__ = 'media_record'

    id = db.Column(db.Integer, primary_key=True)
    article_id = db.Column(db.Integer, db.ForeignKey('article.id', ondelete='CASCADE'), nullable=False)
    original_filename = db.Column(db.String(225))
    mime_type = db.Column(db.String(100))
    relative_path = db.Column(db.String(225), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    file_size = db.Column(db.Integer)

    @property
    def full_path(self) :
        return os.path.join(app.config['UPLOAD_FOLDER'], self.relative_path)
    
    @property
    def file(self) :
        return send_from_directory(os.path.dirname(self.full_path), os.path.basename(self.full_path))
    
# ---------------------------- 辅助函数 -------------------------------
def login_required(f) :
    '''登录验证装饰器'''
    @wraps(f)
    def decorate_function(*args, **kwargs) :
        if not session.get('logged_in') :
            flash('请先登录', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorate_function
    
def get_random_quote():
    """使用 requests 获取随机名言（示例）"""
    try:
        resp = requests.get('https://api.quotable.io/random', timeout=3)
        if resp.status_code == 200:
            data = resp.json()
            return f'“{data["content"]}” — {data["author"]}'
        else:
            return '“代码如诗，博客如家” — 程序员'
    except Exception:
        return '“坚持写作，分享思考” — 博主'

def delete_media_files(article) :
    '''删除文章关联的所有文件'''
    for media_record in article.media_records :
        if os.path.exists(media_record.full_path) :
            os.remove(media_record.full_path)

# ---------------------------- 路由：前台 -----------------------------------
@app.route('/') 
def index() :
    quote = get_random_quote()
    articles = Article.query.order_by(Article.created_at.desc()).all()
    return render_template('index.html', articles=articles, quote=quote)

@app.route('/login', methods=['POST', 'GET'])
def login() :
    '''管理员登录'''
    if request.method == 'POST' :
        password = request.form.get('password', '')
        if hashlib.sha256(password.encode()).hexdigest() == ADMIN_PASSWORD_HASH :
            session['logged_in'] = True
            flash('登录成功', 'success')
            return redirect(url_for('index'))
        else :
            flash('密码错误', 'danger')
    return render_template('login.html')

@app.route('/admin/<int:article_id>', methods=['POST', 'GET'])
@login_required
def admin(article_id) :
    if request.method == 'POST' :
        '''这部分所有的最后的功能回归到post方法'''
        '''这里的功能要分开写！'''
        title = request.form.get('title', '').strip()
        content_md = request.form.get('content_md', '').strip()
        if not title or not content_md :
            flash('内容和文章不能为空', 'warning')
            return render_template('admin.html', article=None)
        if article_id == 0 :
            article = Article(title=title, content_md=content_md)
            db.session.add(article)
        else :
            article = Article.query.get_or_404(article_id)
            article.title = title
            article.content_md = content_md
        db.session.commit()
        
        # 处理上传的文件
        uploaded_files = request.files.getlist('media_files')
        for file in uploaded_files :
            if file and file.filename :
                file.seek(0, 2)
                file_size = file.tell()
                file.seek(0)
                mime_type, _ = mimetypes.guess_type(file.filename)
                media_type = mime_type.split('/', 1)[0]
                if media_type not in ['image', 'audio', 'video'] :
                    flash(f'不支持文件类型：{media_type}', 'warning')
                    continue
                original_filename = secure_filename(file.filename)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                safe_filename = f"{timestamp}_{original_filename}"
                relative_path = os.path.join(f'{media_type}s', safe_filename)  # 相对路径缺少的uploads目录会在media_record.full_path里补全
                media_record = Media_Record(
                    article_id = article.id,
                    relative_path = relative_path,
                    original_filename = file.filename,
                    file_size = file_size,
                    mime_type = mime_type
                )
                file.save(media_record.full_path)
                db.session.add(media_record)
                db.session.commit()
        return redirect(url_for('index'))
    elif article_id == 0 :
        '''articl_id=0意味着新建文章'''
        return render_template('admin.html', article=None)
    else :
        '''这就是编辑文章的部分'''
        article = Article.query.get_or_404(article_id)
        return render_template('admin.html', article=article)
    
@app.route('/admin/<int:article_id>/delete')
@login_required
def delete_article(article_id) :
    '''删除文章及关联媒体文件'''
    article = Article.query.get_or_404(article_id)
    delete_media_files(article)
    db.session.delete(article)
    db.session.commit()
    flash('文章已删除', 'success')
    return redirect(url_for('index'))

@app.route('/browse/<int:article_id>')
def browse(article_id) :
    article = Article.query.get_or_404(article_id)
    return render_template('browse.html', article=article)

# ---------------------------- 路由：后台 -----------------------------------
@app.route('/logout')
def logout() :
    '''退出登录'''
    session.pop('logged_in', None)
    flash('已退出登录', 'info')
    return redirect(url_for('index'))

@app.route('/media/<int:media_record_id>')
def media(media_record_id) :
    media_record = Media_Record.query.get_or_404(media_record_id)
    return media_record.file

# ---------------------------- 初始化数据库 ---------------------------------
with app.app_context() :
    db.create_all()
    

# ------------------------------ 启动 --------------------------------------
if __name__ == '__main__' :
    app.run(host='0.0.0.0', port=8000, debug=True)