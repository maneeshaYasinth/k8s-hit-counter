import flask from Flask
import os 
import redis

app = Flask(__name__)

r = redis.Redis(host=os.getenv('REDIS_HOST', 'localhost'),
    port=6379
    password=os.environ.get("REDIS_PASSWORD", ""),
    decode_responses=True
    )

@app.route('/')
def index():
    count = r.incr('hits')
    return f'Hit counter: {count} .'

@app.route('/health')
def health():
    return "OK\n"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)