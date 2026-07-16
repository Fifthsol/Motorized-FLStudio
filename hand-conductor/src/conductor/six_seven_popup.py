from __future__ import annotations

import random
import tkinter as tk


COLORS = ("#fff200", "#ff3b30", "#00f5d4", "#ffffff", "#ff4fd8", "#54a0ff")


def main() -> None:
    root = tk.Tk()
    root.title("67 SWARM")
    root.attributes("-fullscreen", True)
    root.attributes("-topmost", True)
    root.configure(bg="#050505")
    root.bind("<Escape>", lambda _event: root.destroy())
    root.bind("q", lambda _event: root.destroy())
    root.bind("Q", lambda _event: root.destroy())

    canvas = tk.Canvas(root, bg="#050505", highlightthickness=0)
    canvas.pack(fill="both", expand=True)
    root.update_idletasks()
    width = max(root.winfo_screenwidth(), 640)
    height = max(root.winfo_screenheight(), 480)

    close_button = tk.Button(
        root,
        text="CLOSE  X",
        command=root.destroy,
        bg="#ffffff",
        fg="#000000",
        activebackground="#fff200",
        font=("Arial", 16, "bold"),
        relief="flat",
        padx=18,
        pady=10,
        cursor="hand2",
    )
    close_button.place(relx=1.0, x=-18, y=18, anchor="ne")

    items: list[dict[str, float | int]] = []
    for _ in range(90):
        size = random.randint(24, 110)
        x = random.randint(0, width)
        y = random.randint(0, height)
        item = canvas.create_text(
            x,
            y,
            text="67",
            fill=random.choice(COLORS),
            font=("Arial Black", size, "bold"),
            angle=random.randint(-25, 25),
        )
        items.append({
            "id": item,
            "x": float(x),
            "y": float(y),
            "dx": random.uniform(-5.0, 5.0),
            "dy": random.uniform(-5.0, 5.0),
        })

    def animate() -> None:
        for item in items:
            item["x"] = (float(item["x"]) + float(item["dx"])) % width
            item["y"] = (float(item["y"]) + float(item["dy"])) % height
            canvas.coords(int(item["id"]), float(item["x"]), float(item["y"]))
        root.after(24, animate)

    animate()
    close_button.lift()
    root.mainloop()


if __name__ == "__main__":
    main()
