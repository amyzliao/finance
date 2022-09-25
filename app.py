import os
import datetime

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd


# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


def is_integer(string):
    try:
        int(string)
        return True
    except ValueError:
        return False


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    portfolio = []
    totalstock = 0

    uqsymbols = db.execute("SELECT DISTINCT(symbol) FROM history WHERE id = ? AND symbol IS NOT NULL", session["user_id"])
    for row in uqsymbols:
        price = float(lookup(row["symbol"])["price"])
        shares = int(db.execute("SELECT SUM(shares) FROM history WHERE symbol = ? AND id = ?",
                     row["symbol"], session["user_id"])[0]["SUM(shares)"])
        stockinfo = {
            "symbol": row["symbol"],
            "price": price,
            "shares": shares,
            "totalval": price * shares
        }
        if shares != 0:
            portfolio.append(stockinfo)
        totalstock += stockinfo["totalval"]

    balance = float(db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]["cash"])
    totalasset = totalstock + balance
    return render_template("index.html", portfolio=portfolio, totalstock=totalstock, balance=balance, totalasset=totalasset)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    if request.method == "POST":

        # ensure symbol is submitted and valid
        if not request.form.get("symbol") or not lookup(request.form.get("symbol")):
            return apology("that is not a valid stock symbol")

        # ensure that shares is submitted and is a positive integer
        shares = request.form.get("shares")
        if not shares:
            return apology("must enter number of shares")

        if not is_integer(shares) or int(shares) < 1:
            return apology("you cannot buy that number of shares")
        shares = int(shares)

        # find stock price and calculate total purchase price
        info = lookup(request.form.get("symbol"))
        price = info["price"]
        total = price * shares

        # find how much money user has
        wallet = float(db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]["cash"])

        # ensure user has enough money
        if total > wallet:
            return apology("you can't afford it")

        # get information and track purchase using history table
        id = session["user_id"]
        newwallet = wallet - total
        current_time = datetime.datetime.now()
        month = int(current_time.month)
        day = int(current_time.day)
        year = int(current_time.year)
        db.execute("INSERT INTO history (month, day, year, id, symbol, price, shares, total, new_balance, type) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                     month, day, year, id, info["symbol"], price, shares, total, newwallet, "buy")

        # update users table
        db.execute("UPDATE users SET cash = ? WHERE id = ?", newwallet, session["user_id"])

        username = db.execute("SELECT username FROM users WHERE id = ?", session["user_id"])[0]["username"]
        return render_template("bought.html", month=month, day=day, year=year, symbol=info["symbol"], stockname=info["name"], price=price, shares=shares, total=total, new_balance=newwallet, username=username)

    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    transactions = []

    table = db.execute(
        "SELECT month, day, year, symbol, price, shares, total, new_balance, type FROM history WHERE id = ?", session["user_id"])
    for row in table:
        if not row["symbol"]:
            row["symbol"] = "--"
            row["price"] = 0
            row["shares"] = 0

        if row["type"] == "buy" or row["type"] == "cash remove":
            prefix = "-"
        else:
            prefix = "+"

        if row["type"] == "buy":
            plusshare = "+"
        else:
            plusshare = ""

        item = {
            "type": row["type"],
            "month": row["month"],
            "day": row["day"],
            "year": row["year"],
            "symbol": row["symbol"],
            "price": row["price"],
            "plus": plusshare,
            "shares": row["shares"],
            "prefix": prefix,
            "totalval": row["total"],
            "newbalance": row["new_balance"]
        }

        transactions.append(item)

    return render_template("history.html", transactions=transactions)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":

        stockinfo = lookup(request.form.get("symbol"))

        # ensure symbol is submitted correctly
        if not request.form.get("symbol") or not stockinfo:
            return apology("that is not a valid stock symbol")

        return render_template("quoted.html", name=stockinfo["name"], price=stockinfo["price"], symbol=stockinfo["symbol"])

    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure username not already used
        existusers = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))
        if len(existusers) != 0:
            return apology("that username is taken :(", 400)

        # Ensure password and password confirmation were submitted
        if not request.form.get("password"):
            return apology("must provide password", 400)
        if not request.form.get("confirmation"):
            return apology("must confirm your password", 400)
        # ensure password and confirmation match
        if request.form.get("password") != request.form.get("confirmation"):
            return apology("passwords do not match", 400)

        # add user to database
        db.execute("INSERT INTO users (username, hash) VALUES (?, ?)", request.form.get(
            "username"), generate_password_hash(request.form.get("password")))

        # Remember that this user has logged in
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    if request.method == "POST":
        # get stock portfolio
        stocklist = []
        uqsymbols = db.execute("SELECT DISTINCT(symbol) FROM history WHERE id = ? AND symbol IS NOT NULL", session["user_id"])
        for row in uqsymbols:
            shares = int(db.execute("SELECT SUM(shares) FROM history WHERE symbol = ? AND id = ?",
                         row["symbol"], session["user_id"])[0]["SUM(shares)"])
            if shares > 0:
                stocklist.append(row["symbol"])

        # ensure symbol is submitted and valid
        symbol = request.form.get("symbol")
        if symbol not in stocklist:
            return apology("invalid stock")

        # ensure that shares is submitted
        if not request.form.get("shares"):
            return apology("must enter number of shares")

        # ensures shares is positive (it must already be integer via html implementation)
        shares = int(request.form.get("shares"))
        if shares < 1:
            return apology("you cannot sell that number of shares")

        # ensures user owns at least this many shares
        ownedshares = int(db.execute("SELECT SUM(shares) FROM history WHERE symbol = ? AND id = ?",
                             symbol, session["user_id"])[0]["SUM(shares)"])
        if ownedshares < shares:
            return apology("you don't own enough shares")
        if ownedshares == shares:
            stocklist.remove(symbol)

        # find stock price and calculate total revenue
        stock = lookup(symbol)
        price = stock["price"]
        totalrev = price * shares

        # find new user balance
        oldbalance = float(db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]["cash"])
        newbalance = oldbalance + totalrev

        # update history table
        id = session["user_id"]
        current_time = datetime.datetime.now()
        month = int(current_time.month)
        day = int(current_time.day)
        year = int(current_time.year)
        db.execute("INSERT INTO history (month, day, year, id, symbol, price, shares, total, new_balance, type) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                     month, day, year, id, symbol, price, -shares, totalrev, newbalance, "sell")

        # update users table
        db.execute("UPDATE users SET cash = ? WHERE id = ?", newbalance, session["user_id"])

        username = db.execute("SELECT username FROM users WHERE id = ?", session["user_id"])[0]["username"]
        return render_template("sold.html", stocklist=stocklist, month=month, day=day, year=year, symbol=symbol, stockname=stock["name"], price=price, shares=shares, total=totalrev, new_balance=newbalance, username=username)

    else:
        # get stock portfolio
        stocklist = []
        uqsymbols = db.execute("SELECT DISTINCT(symbol) FROM history WHERE id = ? AND symbol IS NOT NULL", session["user_id"])
        for row in uqsymbols:
            shares = int(db.execute("SELECT SUM(shares) FROM history WHERE symbol = ? AND id = ?",
                         row["symbol"], session["user_id"])[0]["SUM(shares)"])
            if shares > 0:
                stocklist.append(row["symbol"])
        return render_template("sell.html", stocklist=stocklist)


@app.route("/modcash", methods=["GET", "POST"])
@login_required
def modcash():
    if request.method == "POST":

        # ensure an amount of cash exists
        if not request.form.get("amount"):
            return apology("must enter an amount")

        # ensure it is a positive amount of cash
        amount = float(request.form.get("amount"))
        if amount <= 0:
            return apology("amount must be a positive number")

        # find new balance
        oldbalance = float(db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]["cash"])
        if "add" in request.form:
            newbalance = oldbalance + amount
            mod = "added"
            type = "cash add"
        else:
            newbalance = oldbalance - amount
            if newbalance < 0:
                return apology("you do not have enough cash")
            mod = "removed"
            type = "cash remove"

        # update history table
        id = session["user_id"]
        current_time = datetime.datetime.now()
        month = int(current_time.month)
        day = int(current_time.day)
        year = int(current_time.year)
        db.execute("INSERT INTO history (month, day, year, id, total, new_balance, type) VALUES(?, ?, ?, ?, ?, ?, ?)",
                     month, day, year, id, amount, newbalance, type)

        # update users table
        db.execute("UPDATE users SET cash = ? WHERE id = ?", newbalance, session["user_id"])

        # show receipt
        username = db.execute("SELECT username FROM users WHERE id = ?", session["user_id"])[0]["username"]
        return render_template("modcashed.html", mod=mod, amount=amount, new_balance=newbalance, username=username, month=month, day=day, year=year)

    else:
        oldbalance = float(db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]["cash"])
        return render_template("modcash.html", balance=oldbalance)