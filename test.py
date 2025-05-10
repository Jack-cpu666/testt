import tkinter as tk
from tkinter import messagebox
import random
import datetime

class SimpleTestApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Python-to-EXE Test App")
        self.root.geometry("400x350")
        self.root.configure(bg="#f0f0f0")
        
        # Create a frame for the app content
        self.frame = tk.Frame(root, bg="#f0f0f0", padx=20, pady=20)
        self.frame.pack(fill=tk.BOTH, expand=True)
        
        # Display a title
        self.title_label = tk.Label(
            self.frame, 
            text="EXE Converter Test App", 
            font=("Arial", 16, "bold"),
            bg="#f0f0f0"
        )
        self.title_label.pack(pady=(0, 20))
        
        # Current time display
        self.time_label = tk.Label(
            self.frame, 
            text="", 
            font=("Arial", 12),
            bg="#f0f0f0"
        )
        self.time_label.pack(pady=(0, 20))
        self.update_time()
        
        # Create a simple calculator
        self.calc_frame = tk.Frame(self.frame, bg="#f0f0f0")
        self.calc_frame.pack(pady=10)
        
        self.num1_entry = tk.Entry(self.calc_frame, width=10, font=("Arial", 12))
        self.num1_entry.grid(row=0, column=0, padx=5, pady=5)
        
        self.operation_var = tk.StringVar()
        self.operation_var.set("+")
        operations = ["+", "-", "*", "/"]
        self.operation_menu = tk.OptionMenu(self.calc_frame, self.operation_var, *operations)
        self.operation_menu.grid(row=0, column=1, padx=5, pady=5)
        
        self.num2_entry = tk.Entry(self.calc_frame, width=10, font=("Arial", 12))
        self.num2_entry.grid(row=0, column=2, padx=5, pady=5)
        
        self.equals_label = tk.Label(self.calc_frame, text="=", font=("Arial", 12), bg="#f0f0f0")
        self.equals_label.grid(row=0, column=3, padx=5, pady=5)
        
        self.result_label = tk.Label(self.calc_frame, text="", font=("Arial", 12), width=10, 
                                     borderwidth=1, relief="sunken")
        self.result_label.grid(row=0, column=4, padx=5, pady=5)
        
        # Calculate button
        self.calc_button = tk.Button(
            self.frame, 
            text="Calculate", 
            font=("Arial", 12),
            command=self.calculate,
            bg="#4CAF50",
            fg="white",
            padx=20
        )
        self.calc_button.pack(pady=10)
        
        # Random number button
        self.random_button = tk.Button(
            self.frame, 
            text="Generate Random Numbers", 
            font=("Arial", 12),
            command=self.generate_random,
            bg="#2196F3",
            fg="white",
            padx=20
        )
        self.random_button.pack(pady=10)
        
        # Status label
        self.status_label = tk.Label(
            self.frame, 
            text="EXE conversion successful!", 
            font=("Arial", 10, "italic"),
            bg="#f0f0f0", 
            fg="#4CAF50"
        )
        self.status_label.pack(pady=(20, 0))
    
    def update_time(self):
        """Update the time label with current time"""
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.time_label.config(text=f"Current Time: {current_time}")
        self.root.after(1000, self.update_time)
    
    def calculate(self):
        """Perform the calculation"""
        try:
            num1 = float(self.num1_entry.get())
            num2 = float(self.num2_entry.get())
            operation = self.operation_var.get()
            
            if operation == "+":
                result = num1 + num2
            elif operation == "-":
                result = num1 - num2
            elif operation == "*":
                result = num1 * num2
            elif operation == "/":
                if num2 == 0:
                    messagebox.showerror("Error", "Cannot divide by zero!")
                    return
                result = num1 / num2
            
            # Display the result with appropriate formatting
            if result.is_integer():
                self.result_label.config(text=str(int(result)))
            else:
                self.result_label.config(text=f"{result:.2f}")
                
        except ValueError:
            messagebox.showerror("Error", "Please enter valid numbers!")
        except Exception as e:
            messagebox.showerror("Error", f"An error occurred: {str(e)}")
    
    def generate_random(self):
        """Generate random numbers"""
        self.num1_entry.delete(0, tk.END)
        self.num2_entry.delete(0, tk.END)
        self.num1_entry.insert(0, str(random.randint(1, 100)))
        self.num2_entry.insert(0, str(random.randint(1, 100)))

def main():
    root = tk.Tk()
    app = SimpleTestApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()