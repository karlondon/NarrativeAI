# Blog Routes for main.py
# Add these routes to enable blog functionality

from fastapi.responses import HTMLResponse

BLOG_POSTS = {
    "pdf-to-audiobook-guide": {
        "title": "How to Convert PDFs to Audiobooks: Complete Guide",
        "date": "2026-09-16",
        "author": "NarrativeAI Team",
        "excerpt": "Learn how to transform any PDF into a professional audiobook in seconds. Complete guide with tips for best results.",
        "content": """<h2>How to Convert PDFs to Audiobooks: The Complete Guide</h2>
<p>Converting PDFs to audiobooks has never been easier. In this comprehensive guide, we'll walk you through everything you need to know.</p>
<h3>Why Convert PDFs to Audiobooks?</h3>
<ul>
<li>Learn while commuting or exercising</li>
<li>Make content accessible to everyone</li>
<li>Expand your audience for your work</li>
<li>Study more effectively with<li>Study more effectively with<li>Study more effectively w
<li><strong>Upload Your PDF</strong> - Simply drag and drop or click to select your file</li>
<li><strong>Choose Narration Style</strong> - Select single or multi-voice narration</li>
<li><strong>Convert</strong> - Our AI processes it in seconds</li>
<li><strong>Download</strong> - Get your audiobook in MP3 format</li>
</ol>
<h3>Pro Tips for Best Results</h3>
<p>Use clear, well-formatted PDFs for best audio quality. Academic papers, business reports, and novels all work great!</p>
<p>Try multi-voice narration for books with dialogue. It makes the audio much more engaging and professional.</p>
<h3>Pricing</h3>
<p>Get 5 free conversions every day. After that, it's just £1 per download. No subscriptions, no hidden fees.</p>"""
    },
    "best-text-to-speech-tools": {
        "title": "Best Text-to-Speech Tools for Students in 2026",
        "date": "2026-09-16",
        "author": "NarrativeAI Team",
        "excerpt": "Compare the best TTS tools available. See why NarrativeAI stands out for PDF conversion and audiobook creation.",
        "content": """<h2>Best Text-to-Speech Tools for Students in 2026</h2>
<p>Finding the right text-to-speech tool can transform how you study. Let's compare the options.</p>
<h3>What Makes a Great TTS Tool?</h3>
<ul>
<li>Natural, realistic voices</li>
<li>Fast processing</li>
<li>Affordable pricing</li>
<li>No account required</li>
<li>High-quality audio output</li>
</ul>
<h3>NarrativeAI - The Best for PDFs</h3>
<p><strong>Pros:</strong></p>
<ul>
<li>Multi-voice narration for dialogue</li>
<li>Professional AI voices</li>
<li>Lightning fast conversions</li>
<li>5 free per day</li>
<li>Only £1 per download</li>
</ul>
<h3>How Students Use It</h3>
<p>Convert lecture notes into audio. Listen to textbooks while commuting. Study with professional narration instead of robotic voices.</p>
<h3>Conclusion</h3>
<p>For students looking to convert PDFs to audiobooks, NarrativeAI offers the best combination of quality, speed, and affordability. Try it free today!</p>"""
    }
}

# ROUTES TO ADD TO MAIN.PY:

# @app.get("/blog", response_class=HTMLResponse)
# async def blog_index():
#     """Blog homepage listing all posts"""
#     posts_html = ""
#     for slug, post in BLOG_POSTS.items():
#         posts_html += f'''<article>
#         <h3><a href="/blog/{slug}">{post["title"]}</a></h3>
#         <p class="meta">{post["date"]} by {post["author"]}</p>
#         <p>{post["excerpt"]}</p>
#         <a href="/blog/{slug}">Read more →</a>
#         </article>'''
#     
#     html = f'''<!DOCTYPE html>
# <html><head>
# <title>NarrativeAI Blog</title>
# <meta name="description" content="Tips and guides for PDF to audiobook conversion">
# <style>body{{font-family:sans-serif;max-width:800px;margin:50px auto;padding:20px}}article{{margin:30px 0;padding:20px;border:1px solid #ddd;border-radius:8px}}.meta{{color:#666;font-size:0.9em}}</style>
# </head><body>
# <h1>NarrativeAI Blog</h1>
# {posts_html}
# </body></html>'''
#     return html

# @app.get("/blog/{slug}", response_class=HTMLResponse)
# async def blog_post(slug: str):
#     """Individual blog post"""
#     if slug not in BLOG_POSTS:
#         return "<h1>Post not found</h1>", 404
#     
#     post = BLOG_POSTS[slug]
#     html = f'''<!DOCTYPE html>
# <html><head>
# <title>{post["title"]}</title>
# <meta name="description" content="{post['excerpt']}">
# <script async src="https://www.googletagmanager.com/gtag/js?id=G-XXXXXXXXXX"></script>
# <script>window.dataLayer = window.dataLayer || []; function gtag(){{dataLayer.push(arguments);}} gtag('js', new Date()); gtag('config', 'G-XXXXXXXXXX');</script>
# <style>body{{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif;max-width:800px;margin:0 auto;padding:20px;line-height:1.6;color:#333}}h1,h2,h3{{color:#667eea}}a{{color:#667eea;text-decoration:none}}a:hover{{text-decoration:underline}}.meta{{color:#666;font-size:0.9em;margin:10px 0}}.cta{{background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:white;padding:20px;border-radius:8px;margin:30px 0;text-align:center}}.cta a{{color:white;font-weight:bold}}</style>
# </head><body>
# <a href="/">← Back to Home</a>
# <h1>{post["title"]}</h1>
# <p class="meta">{post["date"]} by {post["author"]}</p>
# {post["content"]}
# <div class="cta">
# <h3>Ready to convert your PDFs?</h3>
# <p><a href="/">Try NarrativeAI Free</a> - 5 conversions per day, £1 each after</p>
# </div>
# </body></html>'''
#     return html
