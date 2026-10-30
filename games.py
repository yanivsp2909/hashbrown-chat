"""
🎮 Game logic for the chat server.

No sockets in here: the server calls these classes and sends the text they produce.
Every game has the same shape, so the server can treat them all the same way:
    title, help             text shown to the players
    players                 [first player, second player]
    finished, winner        winner is a player, "draw", or None while playing
    move(player, text)      -> (ok, message)
    looks_like_move(text)   -> True if a plain chat line is really a move ("5", "c3 d4", "w")
    render(viewer)          -> the board as text, from that player's point of view
    state(viewer)           -> the same board as plain data, so a website can draw it
"""
import random


def other_player(players, player):
    return players[1] if player == players[0] else players[0]


# --------------------------------------------------------------------------- Tic-Tac-Toe

class TicTacToe:
    title = "❌⭕ Tic-Tac-Toe"
    help = "Type a number from 1 to 9 to place your mark."
    LINES = [(0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6)]

    def __init__(self, p1, p2):
        self.players = [p1, p2]
        self.marks = {p1: "❌", p2: "⭕"}
        self.cells = [None] * 9
        self.turn = p1
        self.finished = False
        self.winner = None

    def looks_like_move(self, text):
        text = text.strip()
        return len(text) == 1 and text in "123456789"

    def move(self, player, text):
        if player != self.turn:
            return False, "⏳ Not your turn, wait for your opponent."
        if not self.looks_like_move(text):
            return False, "Pick a square with a number from 1 to 9."
        index = int(text.strip()) - 1
        if self.cells[index]:
            return False, "That square is taken."

        mark = self.marks[player]
        self.cells[index] = mark
        if any(all(self.cells[i] == mark for i in line) for line in self.LINES):
            self.finished, self.winner = True, player
        elif all(self.cells):
            self.finished, self.winner = True, "draw"
        else:
            self.turn = other_player(self.players, player)
        return True, ""

    def state(self, viewer):
        return {"game": "ttt", "cells": list(self.cells), "you": self.marks[viewer],
                "your_turn": self.turn == viewer and not self.finished, "finished": self.finished}

    def render(self, viewer):
        rows = []
        for r in range(3):
            cells = [self.cells[r * 3 + c] or f"{r * 3 + c + 1} " for c in range(3)]
            rows.append(" " + " │ ".join(cells))
        lines = ["\n────┼────┼───\n".join(rows)]
        if not self.finished:
            if self.turn == viewer:
                lines.append(f"👉 Your turn ({self.marks[viewer]})")
            else:
                lines.append(f"⏳ Opponent's turn. You are {self.marks[viewer]}")
        return "\n".join(lines)


# --------------------------------------------------------------------------- Connect 4

class Connect4:
    title = "🔴🟡 Connect 4"
    help = "Type a column from 1 to 7. Your piece falls to the bottom. Four in a row wins!"
    ROWS, COLS = 6, 7
    NUMBERS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣"]

    def __init__(self, p1, p2):
        self.players = [p1, p2]
        self.marks = {p1: "🔴", p2: "🟡"}
        self.cells = [None] * (self.ROWS * self.COLS)   # row by row, the top row first
        self.turn = p1
        self.finished = False
        self.winner = None

    def looks_like_move(self, text):
        text = text.strip()
        return len(text) == 1 and text in "1234567"

    def at(self, row, col):
        if 0 <= row < self.ROWS and 0 <= col < self.COLS:
            return self.cells[row * self.COLS + col]
        return None

    def four_from(self, row, col, mark):
        """Does the piece at (row, col) make four in a row in any direction?"""
        for d_row, d_col in ((0, 1), (1, 0), (1, 1), (1, -1)):
            count = 1
            for sign in (1, -1):   # walk both ways from the new piece
                r, c = row + sign * d_row, col + sign * d_col
                while self.at(r, c) == mark:
                    count, r, c = count + 1, r + sign * d_row, c + sign * d_col
            if count >= 4:
                return True
        return False

    def move(self, player, text):
        if player != self.turn:
            return False, "⏳ Not your turn, wait for your opponent."
        if not self.looks_like_move(text):
            return False, "Pick a column with a number from 1 to 7."
        col = int(text.strip()) - 1
        free = [row for row in range(self.ROWS) if self.at(row, col) is None]
        if not free:
            return False, "That column is full."
        row = free[-1]   # the lowest empty spot: pieces fall down
        mark = self.marks[player]
        self.cells[row * self.COLS + col] = mark
        if self.four_from(row, col, mark):
            self.finished, self.winner = True, player
        elif all(self.cells):
            self.finished, self.winner = True, "draw"
        else:
            self.turn = other_player(self.players, player)
        return True, ""

    def state(self, viewer):
        return {"game": "connect4", "cells": list(self.cells), "you": self.marks[viewer],
                "your_turn": self.turn == viewer and not self.finished, "finished": self.finished}

    def render(self, viewer):
        rows = ["".join(self.at(r, c) or "⚪" for c in range(self.COLS)) for r in range(self.ROWS)]
        lines = rows + ["".join(self.NUMBERS)]
        if not self.finished:
            lines.append(f"👉 Your turn ({self.marks[viewer]})" if self.turn == viewer
                         else f"⏳ Opponent's turn. You are {self.marks[viewer]}")
        return "\n".join(lines)


# --------------------------------------------------------------------------- Damka (checkers)

class Checkers:
    title = "🔴🔵 Damka"
    help = ("Move with two squares: from and to, like c3 d4. Captures are mandatory, men can capture "
            "backwards, kings (🟥 🟦) fly any distance. If you can jump again after a capture, you must, "
            "with the same piece.")
    PIECES = {"r": "🔴", "R": "🟥", "b": "🔵", "B": "🟦"}
    DIRECTIONS = [(-1, -1), (-1, 1), (1, -1), (1, 1)]
    MAX_QUIET_MOVES = 60  # this many moves in a row with no capture = draw

    def __init__(self, p1, p2):
        self.players = [p1, p2]
        self.color = {p1: "r", p2: "b"}  # 🔴 starts at the bottom and moves up
        self.board = [[None] * 8 for _ in range(8)]
        for r in range(8):
            for c in range(8):
                if (r + c) % 2 == 1:  # pieces only stand on dark squares
                    if r < 3:
                        self.board[r][c] = "b"
                    elif r > 4:
                        self.board[r][c] = "r"
        self.turn = p1
        self.chain = None  # square of a piece that must keep jumping
        self.quiet = 0
        self.finished = False
        self.winner = None

    @staticmethod
    def square(text):
        """'c3' -> (row, col) on the board, or None if it isn't a square."""
        text = text.strip().lower()
        if len(text) == 2 and text[0] in "abcdefgh" and text[1] in "12345678":
            return 8 - int(text[1]), ord(text[0]) - ord("a")
        return None

    @staticmethod
    def name(pos):
        r, c = pos
        return f"{chr(ord('a') + c)}{8 - r}"

    def looks_like_move(self, text):
        parts = text.split()
        return len(parts) == 2 and all(self.square(p) for p in parts)

    @staticmethod
    def _inside(r, c):
        return 0 <= r < 8 and 0 <= c < 8

    def _captures(self, r, c):
        """Every capture the piece on (r, c) can make: list of (landing square, captured square)."""
        piece = self.board[r][c]
        me = piece.lower()
        found = []
        for dr, dc in self.DIRECTIONS:
            if piece.isupper():  # flying king: slide, jump exactly one enemy, land anywhere after it
                rr, cc = r + dr, c + dc
                while self._inside(rr, cc) and self.board[rr][cc] is None:
                    rr, cc = rr + dr, cc + dc
                if self._inside(rr, cc) and self.board[rr][cc].lower() != me:
                    lr, lc = rr + dr, cc + dc
                    while self._inside(lr, lc) and self.board[lr][lc] is None:
                        found.append(((lr, lc), (rr, cc)))
                        lr, lc = lr + dr, lc + dc
            else:  # man: jump an enemy right next to it, in any of the 4 directions
                mr, mc, lr, lc = r + dr, c + dc, r + 2 * dr, c + 2 * dc
                if (self._inside(lr, lc) and self.board[mr][mc]
                        and self.board[mr][mc].lower() != me and self.board[lr][lc] is None):
                    found.append(((lr, lc), (mr, mc)))
        return found

    def _steps(self, r, c):
        """Normal (non-capture) moves for the piece on (r, c)."""
        piece = self.board[r][c]
        forward = -1 if piece.lower() == "r" else 1
        found = []
        for dr, dc in self.DIRECTIONS:
            if piece.isupper():
                rr, cc = r + dr, c + dc
                while self._inside(rr, cc) and self.board[rr][cc] is None:
                    found.append((rr, cc))
                    rr, cc = rr + dr, cc + dc
            elif dr == forward and self._inside(r + dr, c + dc) and self.board[r + dr][c + dc] is None:
                found.append((r + dr, c + dc))
        return found

    def _pieces(self, color):
        return [(r, c) for r in range(8) for c in range(8)
                if self.board[r][c] and self.board[r][c].lower() == color]

    def _all_captures(self, color):
        return [((r, c), to) for r, c in self._pieces(color) for to, _ in self._captures(r, c)]

    def _can_move(self, color):
        return any(self._captures(r, c) or self._steps(r, c) for r, c in self._pieces(color))

    def _place(self, src, dst):
        self.board[dst[0]][dst[1]] = self.board[src[0]][src[1]]
        self.board[src[0]][src[1]] = None

    def _promote(self, pos):
        r, c = pos
        piece = self.board[r][c]
        if (piece == "r" and r == 0) or (piece == "b" and r == 7):
            self.board[r][c] = piece.upper()
            return True
        return False

    def move(self, player, text):
        if player != self.turn:
            return False, "⏳ Not your turn."
        parts = text.split()
        if len(parts) != 2 or not all(self.square(p) for p in parts):
            return False, "Type a move like c3 d4 (from square, to square)."
        src, dst = self.square(parts[0]), self.square(parts[1])
        color = self.color[player]
        piece = self.board[src[0]][src[1]]
        if not piece or piece.lower() != color:
            return False, f"You don't have a piece on {parts[0]}."
        if self.chain and src != self.chain:
            return False, f"You must keep jumping with the piece on {self.name(self.chain)}."

        if self.chain:
            captures = [(src, to) for to, _ in self._captures(*src)]
        else:
            captures = self._all_captures(color)

        if captures:  # capturing is mandatory
            jumped = next((over for to, over in self._captures(*src) if to == dst), None)
            if jumped is None:
                options = ", ".join(f"{self.name(a)} {self.name(b)}" for a, b in captures[:6])
                return False, f"You must capture! Try: {options}"
            self.board[jumped[0]][jumped[1]] = None
            self._place(src, dst)
            self.quiet = 0
            if self._captures(*dst):  # still a man here: crowning waits until the jumps are over
                self.chain = dst
                return True, f"💥 Jump again with {self.name(dst)}!"
            self._promote(dst)
            self.chain = None
        else:
            if dst not in self._steps(*src):
                return False, "That move isn't allowed."
            self._place(src, dst)
            self._promote(dst)
            self.quiet += 1

        other = other_player(self.players, player)
        if not self._can_move(self.color[other]):  # no pieces left also means no moves
            self.finished, self.winner = True, player
        elif self.quiet >= self.MAX_QUIET_MOVES:
            self.finished, self.winner = True, "draw"
        else:
            self.turn = other
        return True, ""

    def state(self, viewer):
        """board[0] is row 8 (the top), board[7] is row 1. Columns a-h left to right.
        Pieces: "r"/"b" men, "R"/"B" kings, None empty."""
        return {"game": "damka", "board": [row[:] for row in self.board], "you": self.color[viewer],
                "your_turn": self.turn == viewer and not self.finished,
                "must_jump_from": self.name(self.chain) if self.chain else None,
                "finished": self.finished}

    def render(self, viewer):
        header = "  " + "".join(f"{letter} " for letter in "abcdefgh")
        lines = [header]
        for r in range(8):
            row = ""
            for c in range(8):
                piece = self.board[r][c]
                row += self.PIECES[piece] if piece else ("🟫" if (r + c) % 2 else "⬜")
            lines.append(f"{8 - r} {row} {8 - r}")
        lines.append(header)
        if not self.finished:
            color = self.color[viewer]
            direction = "up" if color == "r" else "down"
            turn = "👉 Your turn" if self.turn == viewer else "⏳ Opponent's turn"
            lines.append(f"You are {self.PIECES[color]} (moving {direction})  {turn}")
            if self.chain and self.turn == viewer:
                lines.append(f"💥 Keep jumping with {self.name(self.chain)}!")
        return "\n".join(lines)


# --------------------------------------------------------------------------- Math duel

class MathDuel:
    title = "➗ Math Duel"
    help = ("You both get the same question. Type just the number. First right answer scores, "
            "a wrong answer locks you out of that question. First to 3 wins.")
    TARGET = 3
    MAX_QUESTIONS = 9

    def __init__(self, p1, p2):
        self.players = [p1, p2]
        self.score = {p1: 0, p2: 0}
        self.asked = 0
        self.last = None  # (who scored or None, question, answer) for the previous question
        self.finished = False
        self.winner = None
        self._new_question()

    def _new_question(self):
        self.asked += 1
        self.locked = set()  # players who already answered this one wrong
        op = random.choice("+-×÷")
        if op == "+":
            a, b = random.randint(10, 99), random.randint(10, 99)
            answer = a + b
        elif op == "-":
            a = random.randint(20, 99)
            b = random.randint(1, a)
            answer = a - b
        elif op == "×":
            a, b = random.randint(2, 12), random.randint(2, 15)
            answer = a * b
        else:
            b, answer = random.randint(2, 12), random.randint(2, 12)
            a = b * answer
        self.question, self.answer = f"{a} {op} {b}", answer

    def looks_like_move(self, text):
        digits = text.strip()
        if digits.startswith("-"):  # one minus sign at most
            digits = digits[1:]
        return 1 <= len(digits) <= 6 and digits.isascii() and digits.isdigit()

    def move(self, player, text):
        if self.finished:
            return False, "The game is over."
        if not self.looks_like_move(text):
            return False, "Type just the number."
        if player in self.locked:
            return False, "🔒 You already missed this one. Wait for the next question."
        if int(text.strip()) == self.answer:
            self.score[player] += 1
            self.last = (player, self.question, self.answer)
            self._next()
            return True, ""
        self.locked.add(player)
        if len(self.locked) == 2:  # both missed it
            self.last = (None, self.question, self.answer)
            self._next()
            return True, ""
        return False, "❌ Wrong! You're locked out of this question."

    def _next(self):
        p1, p2 = self.players
        if max(self.score.values()) >= self.TARGET or self.asked >= self.MAX_QUESTIONS:
            self.finished = True
            if self.score[p1] == self.score[p2]:
                self.winner = "draw"
            else:
                self.winner = p1 if self.score[p1] > self.score[p2] else p2
        else:
            self._new_question()

    def state(self, viewer):
        them = other_player(self.players, viewer)
        last = None
        if self.last:
            who, question, answer = self.last
            last = {"question": question, "answer": answer,
                    "scored": "you" if who == viewer else "them" if who else "nobody"}
        return {"game": "math", "question": None if self.finished else self.question,
                "round": self.asked, "max_rounds": self.MAX_QUESTIONS, "target": self.TARGET,
                "you": self.score[viewer], "them": self.score[them],
                "locked_out": viewer in self.locked, "last": last, "finished": self.finished}

    def render(self, viewer):
        them = other_player(self.players, viewer)
        lines = [f"Score: you {self.score[viewer]} - {self.score[them]} them   (first to {self.TARGET})"]
        if self.last:
            who, question, answer = self.last
            if who == viewer:
                lines.append(f"✅ You got it! {question} = {answer}")
            elif who:
                lines.append(f"⚡ They got it first: {question} = {answer}")
            else:
                lines.append(f"😶 Nobody got it: {question} = {answer}")
        if not self.finished:
            lines.append(f"❓ Question {self.asked}/{self.MAX_QUESTIONS}:   {self.question} = ?")
        return "\n".join(lines)


# --------------------------------------------------------------------------- Wordle (solo)

WORDS = [w for w in """
apple brave chair dance eagle flame grape house juice knife lemon mango night ocean piano queen
river snake tiger voice water youth zebra bread cloud dream earth field ghost heart light money
paper plant power radio shirt smile sound space stone storm sugar table teeth train truth world
write young about above actor adult again alarm album alien angel anger angry apart arena audio
award baker basic beach begin below birth black blade blank blast blend blind block blood board
boost brain brand brick bring broad brown brush build bunch candy carry catch cause chain chalk
charm chart chase cheap check chess chest chief child chill civil claim class clean clear click
climb clock close coach coast count court cover craft crash crazy cream crime crowd crown curve
cycle daily delay dirty dozen draft drama drink drive eager early elbow empty enemy enjoy entry
equal error event exact extra faith false fancy feast fight final first flash floor focus force
frame fresh front frost fruit funny giant glass globe glory grace grade grand grass great green
guard guess guest guide habit happy heavy hello honey horse hotel human humor image index input
issue jelly joint judge knock label large laser later laugh layer learn level limit lucky lunch
magic major maker march match medal metal minor model motor mount mouse mouth movie music nerve
never noise north novel nurse offer often order other owner panel party patch peace phone photo
piece pilot pitch pizza place plane plate point pound press price pride prize proof proud quick
quiet raise range rapid reach ready relax reply rider right robot rough round route royal salad
scale scene score sense serve seven shade shake shape share sharp sheep shelf shell shift shine
short sight skill sleep slice slide small smart smoke solid solve sorry south spare speak speed
spend spice spoon sport staff stage stamp stand start steam steel stick still stock store story
study style sunny super sweet swing sword taste teach thank theme thick thing think throw thumb
title toast today token topic total touch tough tower track trade trend trial trick truck trust
twice uncle under union until upper upset usual value video virus visit vital waste watch wheel
while white whole woman worry worth wrong yield
""".split() if len(w) == 5]


class Wordle:
    title = "🟩 Wordle"
    help = ("Guess the secret 5-letter English word in 6 tries with /g word. "
            "🟩 right letter, right spot   🟨 in the word, wrong spot   ⬛ not in the word")
    MAX_TRIES = 6

    def __init__(self):
        self.answer = random.choice(WORDS)
        self.guesses = []  # list of (word, colors)
        self.finished = False
        self.won = False

    @staticmethod
    def score(guess, answer):
        """Colors for each letter. Two passes so double letters are counted correctly."""
        colors = ["⬛"] * 5
        left = []
        for i in range(5):
            if guess[i] == answer[i]:
                colors[i] = "🟩"
            else:
                left.append(answer[i])
        for i in range(5):
            if colors[i] != "🟩" and guess[i] in left:
                colors[i] = "🟨"
                left.remove(guess[i])
        return colors

    def guess(self, word):
        word = word.strip().lower()
        if self.finished:
            return False, "This game is over. /wordle to play again."
        if len(word) != 5 or not word.isascii() or not word.isalpha():
            return False, "Guesses must be 5 English letters, like /g crane"
        if any(word == g for g, _ in self.guesses):
            return False, "You already tried that one."
        self.guesses.append((word, self.score(word, self.answer)))
        if word == self.answer:
            self.finished, self.won = True, True
        elif len(self.guesses) >= self.MAX_TRIES:
            self.finished = True
        return True, ""

    def reward(self):
        """Fewer tries = more tokens: 1 try 60, 2 tries 50 ... 6 tries 10."""
        return 70 - 10 * len(self.guesses) if self.won else 0

    def state(self, viewer=None):
        names = {"🟩": "green", "🟨": "yellow", "⬛": "gray"}
        return {"game": "wordle", "max_tries": self.MAX_TRIES, "finished": self.finished, "won": self.won,
                "guesses": [{"word": word, "colors": [names[c] for c in colors]}
                            for word, colors in self.guesses]}

    def share(self):
        """The colored grid without the letters, safe to show everyone."""
        return "\n".join("".join(colors) for _, colors in self.guesses)

    def render(self):
        lines = []
        for word, colors in self.guesses:
            lines.append("".join(colors) + "   " + " ".join(word.upper()))
        lines += ["⬜⬜⬜⬜⬜"] * (self.MAX_TRIES - len(self.guesses))
        absent = sorted({ch.upper() for word, colors in self.guesses
                         for ch, color in zip(word, colors) if color == "⬛"}
                        - {ch.upper() for word, colors in self.guesses
                           for ch, color in zip(word, colors) if color != "⬛"})
        if absent:
            lines.append("Not in the word: " + " ".join(absent))
        if not self.finished:
            lines.append(f"Try {len(self.guesses) + 1}/{self.MAX_TRIES}: /g word")
        return "\n".join(lines)
