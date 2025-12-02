# Termux-Setup

### Auto-Heavy + Auto-Correct + Auto-Maintain Edition

---

## ⚠️ সতর্কবার্তা (Critical Warning)

এই স্ক্রিপ্ট অত্যন্ত অটোমেটেড ও শক্তিশালী।  
এটি স্বয়ংক্রিয়ভাবে heavy install, update, auto-fix, rollback, backup এবং background maintenance চালায়।  
নতুন ব্যবহারকারীদের জন্য সুপারিশ করা হয় না।

---

## ✨ Features
- 🔥 Auto Heavy Installer  
- 🤖 Auto-Correct (Command + Package Name)  
- 🔍 Fuzzy Package Detection  
- 🔁 Auto-Maintain (background)  
- 📦 Auto Git Clone / Update / Rollback  
- 🧠 Smart Runner System  
- 🛡️ Backup System  

---

## 🛑 Security Warning
স্ক্রিপ্টটি নিচের পেন্টেস্ট টুল ইনস্টল করে:
Nmap, Hydra, SQLMap, Metasploit, OpenVPN, Tor, Proxychains, ইত্যাদি।

✔ বৈধ ব্যবহার:  
- নিজের নেটওয়ার্ক  
- নিজের অনুমতি  
- শেখার উদ্দেশ্যে  

❌ অবৈধ স্ক্যান/হ্যাক → অপরাধ  
❌ ডেভেলপার দায়ী নয়  

---

## 🤖 Auto-Correct Info
ভুল লিখলে ঠিক করে:
- `apt updata` → `apt update`  
- `pkg insatll` → `pkg install`  

প্যাকেজ নেম ভুল হলে fuzzy match দিয়ে সঠিক নাম বসায়।

---

## 🔁 Auto-Maintain
Termux খুললেই ব্যাকগ্রাউন্ডে চালায়:
- Self Update  
- Tool Manager  
- Git Update  
- Rollback System  
- Battery-aware logic  

---

## 🗂️ Backup & Rollback
অটো ব্যাকআপ লোকেশন:
```
~/tool-backups/
```
স্টোরেজ বেশি লাগতে পারে।

---

## ⚠️ Disclaimer
এই প্রজেক্ট "AS IS" দেওয়া —  
ডেটা লস, ক্ষতি, আইনি সমস্যা, ব্রিক হওয়া—  
কোনো কিছুর জন্য ডেভেলপার দায় নেবে না।

ব্যবহারকারী নিজ দায়িত্বে ব্যবহার করবেন।

---

## 📌 Requirements
- ✔ 6GB+ ফ্রি স্টোরেজ  
- ✔ 50%+ ব্যাটারি বা চার্জার  
- ✔ Fast Internet  

---
# এক ক্লিকে ইনস্টলেশন 

```bash

pkg update
pkg upgrade
apt update
apt upgrade -y
pkg install python
pkg install python2
pkg install git
pkg install git
pkg install python
pkg install python2
pkg install python3
pkg install ternux-api
pkg install php
pkg update -y && pkg upgrade -y
pkg install python git -y

git clone https://github.com/piyas2025/Termux-Setup.git

cd Termux-Setup

python3 Termux-Setup.py

```
