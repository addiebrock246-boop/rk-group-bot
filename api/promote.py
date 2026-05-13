import os, json, random, requests as req

BOT_TOKEN = "8808046020:AAEjfprJIKHe7y5TZJckjL22b2yXyM4gKfQ"
GROUP_CHAT_ID = os.environ.get("GROUP_CHAT_ID", "")
UPSTASH_URL = os.environ.get("UPSTASH_REDIS_REST_URL", "")
UPSTASH_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "")

def kv_get(key):
    if not UPSTASH_URL: return None
    url = f"{UPSTASH_URL}/get/{key}"
    headers = {"Authorization": f"Bearer {UPSTASH_TOKEN}"}
    try:
        resp = req.get(url, headers=headers, timeout=5)
        data = resp.json()
        return data.get("result")
    except:
        return None

# Poori player name list (wahi 1000+ names)
PLAYER_NAMES = [
    "James", "John", "Robert", "Michael", "William", "David", "Richard", "Joseph", "Thomas",
    "Charles", "Christopher", "Daniel", "Matthew", "Anthony", "Mark", "Donald", "Steven", "Paul",
    "Andrew", "Joshua", "Kenneth", "Kevin", "Brian", "George", "Timothy", "Ronald", "Edward",
    "Jason", "Jeffrey", "Ryan", "Jacob", "Gary", "Nicholas", "Eric", "Jonathan", "Stephen",
    "Larry", "Justin", "Scott", "Brandon", "Benjamin", "Samuel", "Raymond", "Gregory", "Frank",
    "Alexander", "Patrick", "Jack", "Dennis", "Jerry", "Tyler", "Aaron", "Jose", "Adam", "Nathan",
    "Henry", "Douglas", "Zachary", "Peter", "Kyle", "Ethan", "Walter", "Noah", "Jeremy",
    "Christian", "Keith", "Roger", "Terry", "Gerald", "Harold", "Sean", "Austin", "Carl",
    "Arthur", "Lawrence", "Dylan", "Jesse", "Jordan", "Bryan", "Billy", "Joe", "Bruce", "Albert",
    "Willie", "Gabriel", "Logan", "Alan", "Juan", "Wayne", "Roy", "Ralph", "Randy", "Eugene",
    "Vincent", "Russell", "Elijah", "Louis", "Bobby", "Philip", "Johnny",
    "Mary", "Patricia", "Jennifer", "Linda", "Barbara", "Elizabeth", "Susan", "Jessica", "Sarah",
    "Karen", "Lisa", "Nancy", "Betty", "Margaret", "Sandra", "Ashley", "Dorothy", "Kimberly",
    "Emily", "Donna", "Michelle", "Carol", "Amanda", "Melissa", "Deborah", "Stephanie", "Rebecca",
    "Sharon", "Laura", "Cynthia", "Kathleen", "Amy", "Angela", "Shirley", "Anna", "Brenda",
    "Pamela", "Emma", "Nicole", "Helen", "Samantha", "Katherine", "Christine", "Debra", "Rachel",
    "Carolyn", "Janet", "Catherine", "Maria", "Heather", "Diane",
    "Aarav", "Vivaan", "Aditya", "Vihaan", "Arjun", "Sai", "Reyansh", "Krishna", "Ayaan",
    "Ishaan", "Shaurya", "Atharv", "Dhruv", "Kabir", "Rudra", "Kartik", "Rohan", "Aryan",
    "Dev", "Mohammed", "Ananya", "Diya", "Prisha", "Aadhya", "Saanvi", "Anika", "Pari",
    "Myra", "Ira", "Kiara", "Siya", "Riya", "Tanvi", "Avni", "Aarohi", "Anvi", "Jiya",
    "Navya", "Shanaya", "Vanya", "Tara", "Meera", "Sara", "Ishita", "Lavanya",
    "Raj", "Rahul", "Vikram", "Siddharth", "Manish", "Nitin", "Deepak", "Sunil", "Suresh",
    "Rajesh", "Mahesh", "Rakesh", "Dinesh", "Prakash", "Anil", "Vijay", "Sanjay", "Ajay",
    "Abhishek", "Amit", "Pradeep", "Sachin", "Gaurav", "Kunal", "Rohit", "Akshay",
    "Naveen", "Tarun", "Vivek", "Neha", "Pooja", "Shweta", "Kavita", "Rashmi", "Nisha",
    "Sunita", "Anjali", "Preeti", "Ritu", "Smita", "Komal", "Mona", "Sonali", "Kajal",
    "Madhuri", "Shilpa", "Raveena", "Karishma", "Priyanka", "Deepika", "Alia", "Radhika",
    "Suhana", "Kiara", "Nora",
    "Omar", "Ahmed", "Ali", "Hassan", "Hussein", "Mohamed", "Youssef", "Khaled", "Tarek",
    "Mustafa", "Ibrahim", "Abdullah", "Salman", "Fahad", "Majed", "Nasser", "Saeed", "Adel",
    "Bilal", "Hamza", "Zaid", "Yahya", "Karim", "Rashid", "Samir", "Tamer", "Walid",
    "Fadi", "Hadi", "Jad", "Layth", "Mazin", "Nabil", "Osama", "Rami", "Saif",
    "Yasser", "Aisha", "Fatima", "Noura", "Layla", "Mona", "Huda", "Samira", "Yasmin",
    "Dalia", "Rania", "Hana", "Reem", "Suha", "Amal", "Habiba", "Nadia", "Leila",
    "Salma", "Zeina", "Nada", "Jumana", "Rasha", "Maha", "Hala", "Sahar", "Lina",
    "Dana", "Mira", "Farah", "Noor", "Alaa", "Rawan", "Sana", "May", "Laila",
    "Bushra", "Souad", "Asma", "Khadeeja", "Mariam", "Aya", "Ruba", "Shireen"
]

def handler(request):
    if not GROUP_CHAT_ID:
        return {"statusCode": 500, "body": "GROUP_CHAT_ID not set"}

    data = kv_get("official_bots")
    if not data:
        return {"statusCode": 200, "body": json.dumps({"message": "No official bots"})}

    bots = json.loads(data)
    if not bots:
        return {"statusCode": 200, "body": json.dumps({"message": "No bots configured"})}

    bot_config = random.choice(bots)
    player = random.choice(PLAYER_NAMES)
    amount = round(random.uniform(100, 5000), 2)

    text = (
        f"🔥💎 <b>{bot_config['name']}</b> 💎🔥\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🎰 Player <b>{player}</b> just won <b>{amount} {bot_config['currency']}</b>!\n"
        f"💰 Play now and earn real {bot_config['currency']}.\n"
        f"🚀 Start: {bot_config['link']}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>1000+ players earning daily!</i>"
    )

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    req.post(url, json={"chat_id": GROUP_CHAT_ID, "text": text, "parse_mode": "HTML"}, timeout=10)

    return {"statusCode": 200, "body": json.dumps({"ok": True})}
