import os
import shutil
import sqlite3
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.recycleview import RecycleView


class FoodLoggerApp(App):
    def build(self):
        self.title = "USDA Staples Food Logger"

        # Setup paths for Android sandbox
        self.data_dir = self.user_data_dir
        os.makedirs(self.data_dir, exist_ok=True)
        self.db_path = os.path.join(self.data_dir, "foods.db")

        # Copy pre-packaged database from source to app data directory if it doesn't exist
        bundled_db = "foods.db"
        if not os.path.exists(self.db_path) and os.path.exists(bundled_db):
            shutil.copy(bundled_db, self.db_path)

        layout = BoxLayout(orientation='vertical', padding=15, spacing=10)

        self.status_label = Label(text="Database Ready. Search a staple below:", size_hint_y=0.15)
        layout.add_widget(self.status_label)

        # Search Input
        self.search_input = TextInput(hint_text="e.g. Milk, Apple, Flour, Honey", multiline=False, size_hint_y=0.15)
        self.search_input.bind(on_text_validate=self.search_food)
        layout.add_widget(self.search_input)

        # Search Button
        btn_search = Button(text="Search Database", size_hint_y=0.15, on_press=self.search_food)
        layout.add_widget(btn_search)

        # Results Display Area
        self.results_label = Label(text="[No search executed yet]", halign="center", valign="middle", size_hint_y=0.55)
        self.results_label.bind(texture_size=self.results_label.setter('text_size'))
        layout.add_widget(self.results_label)

        return layout

    def search_food(self, instance):
        query = self.search_input.text.strip()
        if not query:
            self.status_label.text = "Please enter a search term"
            return

        if not os.path.exists(self.db_path):
            self.results_label.text = "Error: Database file not found in device storage."
            return

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Query database using SQL LIKE for fuzzy matching
            cursor.execute(
                "SELECT name, category, calories, protein, carbs, fat FROM foods WHERE name LIKE ?",
                (f"%{query}%",)
            )
            rows = cursor.fetchall()
            conn.close()

            if rows:
                result_text = f"Found {len(rows)} match(es):\n\n"
                for row in rows:
                    name, cat, cal, pro, carb, fat = row
                    result_text += f"• {name} ({cat})\n  Calories: {cal} kcal | P: {pro}g | C: {carb}g | F: {fat}g\n\n"
                self.results_label.text = result_text.strip()
                self.status_label.text = f"Query successful for '{query}'"
            else:
                self.results_label.text = f"No foods found matching '{query}'."
                self.status_label.text = "Try searching: Milk, Oats, Honey, Egg"

        except Exception as e:
            self.status_label.text = "Database query failed"
            self.results_label.text = str(e)


if __name__ == '__main__':
    FoodLoggerApp().run()