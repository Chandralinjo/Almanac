import sqlite3
import os

def create_food_database():
    db_name = "foods.db"
    if os.path.exists(db_name):
        os.remove(db_name)

    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()

    # Create table schema
    cursor.execute('''
        CREATE TABLE foods (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT,
            calories REAL,
            protein REAL,
            carbs REAL,
            fat REAL
        )
    ''')

    # Representative USDA staple items (Calories, Protein, Carbs, Fat per 100g)
    staples = [
        ("Whole Milk", "Dairy", 61, 3.2, 4.8, 3.3),
        ("Eggs (Whole, Raw)", "Dairy & Eggs", 143, 12.6, 0.7, 9.5),
        ("All-Purpose Flour", "Grains", 364, 10.3, 76.3, 1.0),
        ("White Rice (Cooked)", "Grains", 130, 2.7, 28.2, 0.3),
        ("Oats (Rolled)", "Grains", 389, 16.9, 66.3, 6.9),
        ("Banana", "Fruits", 89, 1.1, 22.8, 0.3),
        ("Apple (Raw with skin)", "Fruits", 52, 0.3, 13.8, 0.2),
        ("Broccoli (Raw)", "Vegetables", 34, 2.8, 6.6, 0.4),
        ("Spinach (Raw)", "Vegetables", 23, 2.9, 3.6, 0.4),
        ("Olive Oil", "Oils & Fats", 884, 0.0, 0.0, 100.0),
        ("Butter", "Oils & Fats", 717, 0.9, 0.1, 81.1),
        ("Honey", "Sweeteners", 304, 0.3, 82.4, 0.0)
    ]

    cursor.executemany('''
        INSERT INTO foods (name, category, calories, protein, carbs, fat)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', staples)

    conn.commit()
    conn.close()
    print("Successfully created 'foods.db' with USDA staple data!")

if __name__ == "__main__":
    create_food_database()