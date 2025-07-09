import customtkinter as ctk
import pandas as pd
from PIL import Image
import pystray
from pystray import MenuItem as item
import threading
import configparser
from datetime import date
import os
import sys
from winotify import Notification, audio


def resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller"""
    base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


# --- Constants ---
SETTINGS_FILE = "settings.ini"
LOG_FILE = "water_log.xlsx"
ICON_FILE = resource_path("icon.ico")


class WaterReminderApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # --- App State ---
        self.daily_total = 0
        self.interval_minutes = 30
        self.cup_name = "cup"
        self.timer_id = None
        self.tray_icon = None

        # --- Load Initial Data ---
        self.load_settings()
        self.load_or_create_log()

        # --- Window Configuration ---
        self.title("Hydration Reminder")
        self.geometry("400x450")
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")

        # Set window icon
        if os.path.exists(ICON_FILE):
            self.iconbitmap(ICON_FILE)

        # --- Widget Creation ---
        self.create_widgets()
        self.update_display()

        # --- System Tray & Timer ---
        self.create_tray_icon()
        self.start_reminder_timer()

        # --- Window Behavior ---
        # Intercept the close button and minimize to tray instead
        self.protocol("WM_DELETE_WINDOW", self.hide_to_tray)
        # Handle minimize button click
        self.bind("<Unmap>", self.on_minimize)

    def load_settings(self):
        """Loads settings from settings.ini or creates a default one."""
        config = configparser.ConfigParser()
        if not os.path.exists(SETTINGS_FILE):
            # Create default settings
            config["Settings"] = {
                "interval_minutes": "30",
                "cup_name": "cup",
                "cup_amount_ml": "250",
            }
            with open(SETTINGS_FILE, "w") as configfile:
                config.write(configfile)

        config.read(SETTINGS_FILE)
        self.interval_minutes = int(
            config.get("Settings", "interval_minutes", fallback=30)
        )
        self.cup_name = config.get("Settings", "cup_name", fallback="cup")
        # self.cup_amount_ml is loaded but not used in this simplified version

    def save_settings(self):
        """Saves current settings to the .ini file."""
        config = configparser.ConfigParser()
        config.read(SETTINGS_FILE)
        config["Settings"]["interval_minutes"] = str(self.interval_minutes)
        with open(SETTINGS_FILE, "w") as configfile:
            config.write(configfile)

    def load_or_create_log(self):
        """Loads today's progress from the Excel file or initializes it."""
        today = date.today().strftime("%Y-%m-%d")
        try:
            df = pd.read_excel(LOG_FILE)
            # Make sure the 'Date' column is in datetime format for proper comparison
            df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")

            today_entry = df[df["Date"] == today]
            if not today_entry.empty:
                self.daily_total = int(today_entry.iloc[0]["Total Cups"])
            else:
                self.daily_total = 0
        except FileNotFoundError:
            # If the file doesn't exist, we start at 0
            self.daily_total = 0
        except Exception as e:
            print(f"Error loading log file: {e}")
            self.daily_total = 0

    def save_log(self):
        """Saves the current progress to the Excel file for today's date."""
        today = date.today().strftime("%Y-%m-%d")
        new_row = {"Date": today, "Total Cups": self.daily_total}

        try:
            df = pd.read_excel(LOG_FILE)
            df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")

            # Find if today's entry exists
            if today in df["Date"].values:
                df.loc[df["Date"] == today, "Total Cups"] = self.daily_total
            else:
                # Append new row
                df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        except FileNotFoundError:
            # Create new DataFrame if file does not exist
            df = pd.DataFrame([new_row])

        # Save to excel
        df.to_excel(LOG_FILE, index=False)

    def create_widgets(self):
        """Creates and places all the GUI widgets."""
        main_frame = ctk.CTkFrame(self, corner_radius=15)
        main_frame.pack(pady=20, padx=20, fill="both", expand=True)

        title_label = ctk.CTkLabel(
            main_frame,
            text="Hydration Reminder",
            font=ctk.CTkFont(size=28, weight="bold"),
        )
        title_label.pack(pady=(10, 20))

        self.progress_label = ctk.CTkLabel(
            main_frame, text="", font=ctk.CTkFont(size=20)
        )
        self.progress_label.pack(pady=10)

        button_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        button_frame.pack(pady=20)

        drunk_button = ctk.CTkButton(
            button_frame,
            text=f"Drank",
            command=self.drank_water,
            width=150,
            height=50,
            font=ctk.CTkFont(size=16),
        )
        drunk_button.pack(side="left", padx=10)

        peed_button = ctk.CTkButton(
            button_frame,
            text="Peed (-1)",
            command=self.peed,
            width=100,
            height=50,
            fg_color="#D32F2F",
            hover_color="#B71C1C",
            font=ctk.CTkFont(size=16),
        )
        peed_button.pack(side="left", padx=10)

        settings_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        settings_frame.pack(pady=20, fill="x", padx=20)

        interval_label_text = ctk.CTkLabel(
            settings_frame,
            text="Reminder Interval (minutes):",
            font=ctk.CTkFont(size=14),
        )
        interval_label_text.pack()

        self.interval_slider = ctk.CTkSlider(
            settings_frame,
            from_=1,
            to=120,
            number_of_steps=23,
            command=self.update_interval_label,
        )
        self.interval_slider.set(self.interval_minutes)
        self.interval_slider.pack(pady=(5, 0), fill="x")

        self.interval_value_label = ctk.CTkLabel(
            settings_frame,
            text=f"{self.interval_minutes} minutes",
            font=ctk.CTkFont(size=12),
        )
        self.interval_value_label.pack()

    def update_display(self):
        """Updates the progress label with the current total."""
        self.progress_label.configure(
            text=f"Today's total: {self.daily_total} {self.cup_name}s"
        )

    def drank_water(self, from_tray=False):
        """Increments water count and saves."""
        self.daily_total += 1
        self.update_display()
        self.save_log()
        print("Logged: Drank 1 cup.")

    def peed(self):
        """Decrements water count and saves."""
        if self.daily_total > 0:
            self.daily_total -= 1
            self.update_display()
            self.save_log()
            print("Logged: Peed (-1 cup).")
        else:
            print("Cannot go below zero.")

    def update_interval_label(self, value):
        """Updates the label for the interval slider and saves the new setting."""
        new_interval = int(value)
        self.interval_minutes = new_interval
        self.interval_value_label.configure(text=f"{new_interval} minutes")
        # Save settings whenever the slider value changes and is released
        self.save_settings()
        # We don't need to restart the timer immediately, the next cycle will pick up the new value
        print(f"Interval updated to {new_interval} minutes.")

    def start_reminder_timer(self):
        """Sets or resets the reminder timer."""
        if self.timer_id:
            self.after_cancel(self.timer_id)

        interval_ms = self.interval_minutes * 60 * 1000
        self.timer_id = self.after(interval_ms, self.show_notification)
        print(f"Next reminder in {self.interval_minutes} minutes.")

    def show_notification(self):
        """Shows a Windows notification and then resets the timer."""
        toast = Notification(
            app_id="Hydration Hero",
            title="Time to Hydrate!",
            msg=f"Hey! It's time to drink one {self.cup_name} of water.",
            icon=os.path.abspath(ICON_FILE),
            duration="long",
        )
        toast.set_audio(audio.Default, loop=False)
        toast.show()

        # Reset the timer for the next notification
        self.start_reminder_timer()

    def create_tray_icon(self):
        """Creates the system tray icon and its menu."""
        image = Image.open(ICON_FILE)
        menu = (
            item("Open", self.show_from_tray, default=True),
            item(f"Drank", self.drank_water_from_tray),
            item(f"Peed", self.peed_from_tray),
            item("Exit", self.exit_app),
        )
        self.tray_icon = pystray.Icon("Hydration Hero", image, "Hydration Hero", menu)

        # Run the tray icon in a separate thread
        tray_thread = threading.Thread(target=self.tray_icon.run, daemon=True)
        tray_thread.start()

    def drank_water_from_tray(self):
        """Wrapper to call drink_water from the tray menu."""
        self.drank_water(from_tray=True)

    def peed_from_tray(self):
        """Wrapper to call drink_water from the tray menu."""
        self.peed()

    def on_minimize(self, event=None):
        """Handle the minimize button click."""
        if self.state() == "iconic":  # 'iconic' is the state for minimized
            self.hide_to_tray()

    def hide_to_tray(self):
        """Hides the main window."""
        self.withdraw()

    def show_from_tray(self):
        """Shows the main window from the system tray."""
        self.deiconify()
        self.lift()
        self.focus_force()

    def exit_app(self):
        """Stops the tray icon and closes the application."""
        if self.timer_id:
            self.after_cancel(self.timer_id)
        if self.tray_icon:
            self.tray_icon.stop()
        self.destroy()


if __name__ == "__main__":
    app = WaterReminderApp()
    app.mainloop()
