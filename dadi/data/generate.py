"""Synthetic Hinglish call-transcript generator for training the scam detector.

Real scam-call transcripts with labels are not publicly available, so we
compose calls from hand-written "moves" (one scammer utterance each) that
mirror scripts reported by I4C, RBI advisories and news coverage. Every move
is tagged with the manipulation tactics it uses.

Honest evaluation: each move's phrasings are split into train/test pools, so
test calls are built from sentences the model never saw. The real-world eval
set (role-played calls) lives in data/roleplay/ and is scored separately.

Usage:  uv run python -m dadi.data.generate --n 4000 --out data/synthetic
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

TACTICS = ["authority", "urgency", "fear", "secrecy", "payment_request", "credential_request", "reward_lure"]
SCAM_TYPES = ["digital_arrest", "kyc_bank", "courier_parcel", "task_job", "investment", "electricity_bill", "lottery_prize"]

SLOTS = {
    "name": ["Sunita ji", "madam", "sir", "aunty ji", "uncle ji", "Mr Sharma", "Mrs Iyer", "beta", "Ramesh ji", "Kavita ji"],
    "officer": ["Inspector Vikram Singh", "Officer Rajesh Kumar", "Inspector Anil Yadav", "DCP Sanjay Mehta",
                "Sub Inspector Pooja Rathore", "Officer Arjun Malhotra", "Inspector Deepak Chauhan"],
    "city": ["Mumbai", "Delhi", "Kolkata", "Hyderabad", "Bangalore", "Lucknow", "Chennai", "Pune"],
    "amount": ["49,999", "1,50,000", "2 lakh", "25,000", "75,000", "9,500", "5 lakh", "3,20,000", "12,000"],
    "item": ["5 passport, 3 credit card aur 200 gram MDMA", "fake passports and drugs", "illegal SIM cards",
             "150 gram drugs aur foreign currency", "laptop aur kuch documents"],
    "bank": ["SBI", "HDFC", "ICICI", "Axis bank", "Bank of Baroda", "PNB", "Kotak"],
    "case_no": ["MH 2034 / 7781", "CBI slash 55 slash 2026", "FIR number 4471", "case number 88 20 14", "NCB 7732"],
    "company": ["Amazon", "Flipkart", "Meesho", "Myntra", "Zomato", "Swiggy"],
    "app": ["AnyDesk", "TeamViewer", "Quick Support", "RustDesk"],
    "stock": ["Tata Power", "Adani", "Reliance", "Zomato IPO", "HDFC", "a new crypto coin"],
    "prize": ["25 lakh", "Tata Nexon car", "iPhone 17", "KBC lottery 35 lakh", "gold coin"],
    "upi": ["verification.cell@ybl", "rbi.refund@okaxis", "cbi.safe@paytm", "kycupdate2026@ibl",
            "customs.clear@oksbi", "taskpay.hr@axl", "prizeclaim@upi", "safeaccount.rbi@okhdfcbank"],
    "phone": ["9876543210", "8123456709", "7002938471", "9988776655", "6203948571", "8899001122"],
    "account": ["503812347761", "34561298007", "91827364550123", "100022334455", "221100998877"],
    "friend": ["Rohit", "Priya", "Aman", "Neha", "Karan", "Sneha"],
    "doctor": ["Dr Mehra", "Dr Rao", "Dr Kapoor", "Dr Fernandes"],
}

# Each scam type: ordered stages; each stage: list of (text, tactics).
SCAMS: dict[str, list[list[tuple[str, list[str]]]]] = {
    "digital_arrest": [
        [("Hello {name}, main {officer} bol raha hoon {city} Crime Branch se.", ["authority"]),
         ("Good afternoon, this is {officer} from CBI {city} office, am I speaking to {name}?", ["authority"]),
         ("Namaste {name}, main TRAI se bol raha hoon, aapka number do ghante mein band ho jayega.", ["authority", "urgency"]),
         ("Hello, {city} cyber cell se call hai, aapke naam pe ek complaint register hui hai.", ["authority", "fear"]),
         ("This call is from Narcotics Control Bureau, {officer} speaking, please confirm your name.", ["authority"]),
         ("Main {officer}, CBI headquarters se, aapka Aadhaar ek money laundering case mein aaya hai.", ["authority", "fear"])],
        [("Aapke Aadhaar se ek parcel bheja gaya hai jisme {item} mila hai.", ["fear"]),
         ("Your Aadhaar is linked to a money laundering case, case number {case_no}.", ["fear", "authority"]),
         ("Aapke naam pe {city} mein ek bank account khula hai jisme crore rupaye ka hawala hua hai.", ["fear"]),
         ("There is an arrest warrant issued in your name by the {city} court.", ["fear", "authority"]),
         ("Aapke number se illegal advertisement aur harassment messages bheje gaye hain, FIR ho chuki hai.", ["fear"]),
         ("Humare paas aapke khilaf supreme court ka order hai, aap abhi digital arrest mein ho.", ["fear", "authority"])],
        [("Aap ye call disconnect nahi karenge, warna local police aapko abhi arrest karegi.", ["fear", "urgency", "secrecy"]),
         ("Do not tell anyone in your family, this is a confidential national security matter.", ["secrecy"]),
         ("Aap video call pe rahiye, camera on rakhiye, aap digital custody mein hain.", ["secrecy", "authority"]),
         ("Kisi ko bhi batana mat, na bete ko na pati ko, warna unko bhi case mein daal denge.", ["secrecy", "fear"]),
         ("Room band kar lijiye aur akele baithiye, investigation chal rahi hai.", ["secrecy"]),
         ("If you hang up now it will be treated as non cooperation and police will reach your home in 30 minutes.", ["fear", "urgency"])],
        [("Aapko verification ke liye apne saare paise RBI safe account mein transfer karne honge.", ["payment_request", "authority"]),
         ("Send {amount} rupees to this UPI {upi} for verification, it will be refunded after investigation.", ["payment_request"]),
         ("Security deposit {amount} abhi transfer kijiye account number {account} mein.", ["payment_request", "urgency"]),
         ("Aapke account ka paisa legal hai ya nahi check karna hai, isliye {amount} is account mein daaliye {account}.", ["payment_request"]),
         ("Bail ke liye {amount} ka payment aaj hi karna padega, warna kal subah arrest.", ["payment_request", "urgency", "fear"])],
        [("Jaldi kijiye, aapke paas sirf 30 minute hain.", ["urgency"]),
         ("Transaction ke baad screenshot bhejiye WhatsApp pe {phone} pe.", ["payment_request"]),
         ("Aapka FD tod ke paisa bhejiye, ye court order hai.", ["payment_request", "authority"]),
         ("Once verified, the money will come back within 24 hours with an RBI clearance certificate.", ["reward_lure", "authority"])],
    ],
    "kyc_bank": [
        [("Hello {name}, main {bank} head office se bol raha hoon.", ["authority"]),
         ("Good morning sir, calling from {bank} KYC department.", ["authority"]),
         ("{name}, aapka {bank} account aaj raat 12 baje block ho jayega.", ["urgency", "fear"]),
         ("Sir, RBI guidelines ke according aapka KYC pending hai.", ["authority", "urgency"]),
         ("Main {bank} customer care se bol rahi hoon, aapke debit card pe issue hai.", ["authority"])],
        [("Aapka PAN card link nahi hai, isliye account freeze ho raha hai.", ["fear", "urgency"]),
         ("Your KYC has expired, your account will be suspended today.", ["fear", "urgency"]),
         ("Aapke credit card pe 49,999 ka suspicious transaction hua hai.", ["fear"]),
         ("Aapke reward points expire ho rahe hain, 5000 rupaye ke points hain.", ["reward_lure", "urgency"])],
        [("Abhi aapke phone pe ek OTP aayega, wo mujhe bata dijiye.", ["credential_request"]),
         ("Please share the OTP you just received to complete verification.", ["credential_request"]),
         ("Play store se {app} download kijiye, main remotely aapka KYC kar dunga.", ["credential_request"]),
         ("Apne debit card ke peeche ka CVV number bataiye.", ["credential_request"]),
         ("Ek link bheja hai SMS pe, usme apna ATM PIN daal dijiye.", ["credential_request"]),
         ("Screen share on kijiye aur apna net banking password type kijiye.", ["credential_request"])],
        [("Jaldi kijiye sir, 10 minute mein account block ho jayega.", ["urgency"]),
         ("Kisi ko call mat kijiye, bank branch jaane ki zarurat nahi hai, main yahin kar dunga.", ["secrecy"]),
         ("Verification charge sirf 10 rupaye hai, is UPI pe bhejiye {upi}.", ["payment_request"]),
         ("Aapka account unfreeze karne ke liye {amount} safe account {account} mein daalna hoga.", ["payment_request"])],
    ],
    "courier_parcel": [
        [("Hello, main FedEx courier se bol raha hoon, aapka parcel {city} customs pe ruka hai.", ["authority"]),
         ("This is DHL international, a parcel in your name has been seized.", ["authority", "fear"]),
         ("{name}, aapka Blue Dart parcel return ho gaya hai, address incomplete hai.", ["urgency"]),
         ("Main customs department se, aapke naam pe Taiwan se ek parcel aaya hai.", ["authority"])],
        [("Parcel mein {item} mila hai, ye serious crime hai.", ["fear"]),
         ("Aapko abhi call {city} police ko transfer kar raha hoon, wo aapse baat karenge.", ["authority", "fear"]),
         ("Customs duty {amount} pending hai, warna parcel destroy ho jayega aur case banega.", ["payment_request", "fear"]),
         ("Parcel redeliver karne ke liye 5 rupaye ka payment karna hai link se.", ["payment_request"])],
        [("Ye link pe click karke apna card number aur OTP daaliye.", ["credential_request"]),
         ("Customs clearance ke liye {upi} pe payment kijiye abhi.", ["payment_request", "urgency"]),
         ("Aaj ke andar clear nahi kiya toh legal action hoga.", ["urgency", "fear"]),
         ("Kisi ko is baare mein mat batana, investigation affect hogi.", ["secrecy"])],
    ],
    "task_job": [
        [("Hello, main {company} HR team se, aapko part time work from home job chahiye?", ["reward_lure"]),
         ("Hi {name}, we have a simple online job, earn 5000 rupees daily from home.", ["reward_lure"]),
         ("Aapka resume select hua hai, sirf YouTube videos like karne hain, per like 50 rupaye.", ["reward_lure"]),
         ("Telegram pe ek task group hai, Google reviews dene ke 150 rupaye milenge.", ["reward_lure"])],
        [("Pehle 3 task free hain, uske baad prepaid task mein 1000 lagao aur 1500 pao.", ["payment_request", "reward_lure"]),
         ("Registration fee sirf 999 hai, fully refundable.", ["payment_request"]),
         ("Aapka commission 12,000 ban gaya hai, withdraw ke liye tax {amount} pay karna hoga.", ["payment_request", "reward_lure"]),
         ("VIP level unlock karne ke liye {amount} deposit kijiye, profit double hoga.", ["payment_request", "reward_lure"])],
        [("Aaj offer khatam ho raha hai, jaldi join kijiye.", ["urgency"]),
         ("Payment is UPI pe kijiye {upi}, receipt Telegram pe bhejiye.", ["payment_request"]),
         ("Aapka account freeze ho gaya hai, unfreeze ke liye {amount} aur lagega.", ["payment_request", "fear"]),
         ("Family ko mat batao, ye confidential scheme hai limited logon ke liye.", ["secrecy"])],
    ],
    "investment": [
        [("Hello {name}, main SEBI registered advisor bol raha hoon.", ["authority"]),
         ("Sir, humara stock tips group hai, daily 20 percent return guaranteed.", ["reward_lure"]),
         ("Hi, I am calling from a trading academy, we have an exclusive IPO allotment for you.", ["reward_lure"]),
         ("Aapko {stock} mein insider tip milega, kal 300 percent upar jayega.", ["reward_lure"])],
        [("Humara app install kijiye, usme {amount} invest kijiye.", ["payment_request"]),
         ("Minimum investment {amount} hai, profit ek hafte mein double.", ["payment_request", "reward_lure"]),
         ("Institutional account mein paisa daalna hai, account number {account}.", ["payment_request"]),
         ("Aapka profit 8 lakh ho gaya hai, withdraw ke liye 20 percent tax pehle bharna hoga.", ["payment_request", "reward_lure"])],
        [("Ye offer sirf aaj ke liye hai, slots khatam ho rahe hain.", ["urgency"]),
         ("Kisi ko mat batana, warna sab log le lenge aur price gir jayega.", ["secrecy"]),
         ("Payment {upi} pe kar dijiye, screenshot WhatsApp kijiye {phone}.", ["payment_request"])],
    ],
    "electricity_bill": [
        [("Dear customer, main bijli vibhag se bol raha hoon.", ["authority"]),
         ("Electricity board se call hai, aapka bijli connection aaj raat 9.30 baje kat jayega.", ["authority", "urgency", "fear"]),
         ("{name}, aapka pichle mahine ka bill update nahi hua hai.", ["fear"])],
        [("Turant is number pe call kijiye {phone} aur bill update karaiye.", ["urgency"]),
         ("{app} download kijiye, main aapka bill update kar deta hoon.", ["credential_request"]),
         ("Sirf 10 rupaye ka payment karna hai, apna card number bataiye.", ["credential_request", "payment_request"]),
         ("Pending amount {amount} abhi {upi} pe bhejiye warna connection kat jayega.", ["payment_request", "urgency"])],
        [("Jaldi kijiye, officer aapke ghar aa raha hai meter kaatne.", ["urgency", "fear"]),
         ("OTP aayega wo batana, tabhi update hoga.", ["credential_request"])],
    ],
    "lottery_prize": [
        [("Congratulations {name}! Aapne KBC lucky draw mein {prize} jeeta hai.", ["reward_lure"]),
         ("Hello, main {company} se, aapka mobile number lucky winner chuna gaya hai, {prize}.", ["reward_lure"]),
         ("You have won {prize} in our anniversary lucky draw sir.", ["reward_lure"])],
        [("Prize claim karne ke liye processing fee {amount} bharna hoga.", ["payment_request"]),
         ("GST aur tax ke {amount} pehle bhejiye, prize kal ghar pe deliver hoga.", ["payment_request"]),
         ("Apna bank account number aur IFSC bataiye, prize money transfer karni hai.", ["credential_request"])],
        [("Ye offer 2 ghante mein expire ho jayega.", ["urgency"]),
         ("Payment {upi} pe kijiye aur is number pe confirm kijiye {phone}.", ["payment_request"]),
         ("Kisi ko mat batana warna prize cancel ho jayega.", ["secrecy"])],
    ],
}

# Legitimate calls, including hard negatives that mention banks, parcels,
# police, KYC and payments the way real people do.
LEGIT: dict[str, list[list[str]]] = {
    "family": [
        ["Hello mummy, main {friend} bol raha hoon, khana kha liya?", "Dadi pranam, kaisi ho aap?",
         "Hi maa, I reached {city} safely.", "Nani, main aapka pota, aaj shaam ko aa raha hoon."],
        ["Aaj office mein bahut kaam tha, weekend pe ghar aaunga.", "Papa ki dawai le li kya aapne?",
         "Bhaiya ki shaadi ki date fix ho gayi, December mein.", "Main aapke liye naya chashma le aaunga."],
        ["Achha chalo, raat ko video call karta hoon.", "Apna dhyaan rakhna, bye.",
         "Kuch chahiye toh bata dena, main online order kar dunga.", "Paise chahiye toh bata dena, GPay kar dunga."],
    ],
    "friend": [
        ["Arre {friend} bol raha hoon, kya scene hai aaj?", "Hey, it's {friend}, are you free this evening?",
         "Oye, kal ka match dekha?", "Bhai notes bhej de na kal ke lecture ke."],
        ["Yaar mera parcel aaj bhi nahi aaya, {company} wale bohot late kar rahe hain.",
         "Kal traffic police ne challan kaat diya, 500 rupaye gaye.", "Mera bank ka KYC karwana hai, branch kitne baje khulti hai?",
         "Movie ke tickets maine book kar liye, tu 300 bhej dena baad mein."],
        ["Chal milte hain shaam ko cafe pe.", "Theek hai, baad mein baat karte hain.", "Okay bye, see you tomorrow."],
    ],
    "bank_genuine": [
        ["Namaste, main {bank} {city} branch se bol rahi hoon, aapka debit card branch mein aa gaya hai.",
         "Hello, this is {bank} home loan department regarding your application.",
         "Good morning, {bank} se courtesy call hai, aapki FD next week mature ho rahi hai."],
        ["Aap apna original PAN aur Aadhaar lekar branch aa jaiye, wahi KYC ho jayega.",
         "Please note, bank kabhi bhi phone pe OTP ya PIN nahi maangta.",
         "Aap net banking se renewal kar sakte hain ya branch visit kar sakte hain.",
         "Your documents are verified, the sanction letter will be emailed."],
        ["Koi aur sawal ho toh branch ke landline pe call kijiye.", "Thank you for banking with us, have a nice day.",
         "Kal 10 se 4 ke beech kabhi bhi aa sakte hain."],
    ],
    "delivery_genuine": [
        ["Hello, {company} delivery se bol raha hoon, aapka order aaya hai.", "Sir, main courier wala, aapke gate pe khada hoon.",
         "Ma'am, your {company} package is out for delivery."],
        ["Ghar pe koi hai? Cash on delivery 649 rupaye hai.", "Location thoda samajh nahi aa raha, landmark bataiye.",
         "OTP app mein dikhega, wo delivery ke time bata dena.", "Main 10 minute mein pahunch jaunga."],
        ["Theek hai, guard ko de deta hoon.", "Okay ma'am, thank you.", "Rating de dena please."],
    ],
    "clinic": [
        ["Hello, {doctor} clinic se bol rahe hain, kal aapka appointment hai.", "Good evening, calling from {city} diagnostics about your reports."],
        ["Kal subah 11 baje aa jaiye, khali pet aana hai.", "Your blood test reports are ready, you can collect them.",
         "Consultation fee 500 hai, counter pe de dijiyega."],
        ["Koi dikkat ho toh clinic pe call kar lijiye.", "Thank you, take care."],
    ],
    "telemarketing": [
        ["Hello sir, {company} se bol rahe hain, aapke liye credit card ka offer hai.", "Sir, new broadband plan launch hua hai, 499 mein unlimited.",
         "Ma'am, insurance ke baare mein 2 minute baat kar sakte hain?"],
        ["Aap interested hain toh humara executive aapke ghar aa jayega documents ke liye.",
         "Ye plan aap app se ya store se le sakte hain.", "Aap chahein toh main brochure WhatsApp kar deta hoon."],
        ["Theek hai sir, disturb karne ke liye sorry.", "Not interested? No problem, thank you."],
    ],
    "college_office": [
        ["Hello, college office se bol rahe hain, aapka ID card ready hai.", "Hi, this is the placement cell, your interview is scheduled for Monday.",
         "Namaste, hostel office se, aapka room allotment ho gaya hai."],
        ["Fees portal pe hi pay kijiye, receipt download kar lijiye.", "Please carry two copies of your resume and college ID.",
         "Warden sir se milke key le lijiye."],
        ["All the best.", "Aur koi query ho toh office aa jaiye."],
    ],
    "utility_genuine": [
        ["Namaste, bijli vibhag se, kal aapke area mein maintenance ke liye 10 se 2 light nahi rahegi.",
         "Hello, gas agency se, aapka cylinder booking confirm hai."],
        ["Bill aap official app ya website se hi bhariye.", "Delivery kal tak ho jayegi, cash ya online de sakte hain."],
        ["Dhanyavaad.", "Thank you ji."],
    ],
    "police_genuine": [
        ["Hello, main {city} police station se constable bol raha hoon, aapka passport verification hai.",
         "Namaste, thane se call hai, aapki gaadi chori ki complaint ka update hai."],
        ["Kal apne original documents lekar thane aa jaiye.", "Aap station aake FIR ki copy le sakte hain, koi fees nahi hai."],
        ["Thana 10 baje khulta hai.", "Theek hai, dhanyavaad."],
    ],
}

FILLERS = ["haan", "ji", "achha", "sir", "madam", "dekhiye", "suniye", "ok", "matlab", "hello"]
SPOKEN = {"0": "zero", "1": "one", "2": "two", "3": "three", "4": "four", "5": "five",
          "6": "six", "7": "seven", "8": "eight", "9": "nine"}


def _speak_digits(s: str) -> str:
    return " ".join(SPOKEN.get(c, c) for c in s)


def _fill(text: str, rng: random.Random) -> str:
    out = text
    for key, values in SLOTS.items():
        token = "{" + key + "}"
        while token in out:
            val = rng.choice(values)
            if key in {"phone", "account"} and rng.random() < 0.4:
                val = _speak_digits(val)
            if key == "upi" and rng.random() < 0.4:
                val = val.replace("@", " at the rate ")
            out = out.replace(token, val, 1)
    return out


def _asr_noise(text: str, rng: random.Random) -> str:
    """Mimic browser speech-to-text: lowercase, no punctuation, dropped words, fillers."""
    words = text.lower().replace(",", "").replace(".", "").replace("?", "").replace("!", "").split()
    words = [w for w in words if rng.random() > 0.05]
    if rng.random() < 0.35:
        words.insert(rng.randrange(len(words) + 1), rng.choice(FILLERS))
    return " ".join(words) if words else text.lower()


def _split_pool(variants: list, rng: random.Random, test_frac: float) -> tuple[list, list]:
    idx = list(range(len(variants)))
    rng.shuffle(idx)
    n_test = max(1, round(len(idx) * test_frac))
    test = [variants[i] for i in idx[:n_test]]
    train = [variants[i] for i in idx[n_test:]]
    return train, test


def build_pools(seed: int, test_frac: float = 0.25) -> dict[str, dict]:
    rng = random.Random(seed)
    pools: dict[str, dict] = {"train": {"scam": {}, "legit": {}}, "test": {"scam": {}, "legit": {}}}
    for stype, stages in SCAMS.items():
        tr, te = zip(*(_split_pool(stage, rng, test_frac) for stage in stages))
        pools["train"]["scam"][stype], pools["test"]["scam"][stype] = list(tr), list(te)
    for ltype, stages in LEGIT.items():
        tr, te = zip(*(_split_pool(stage, rng, test_frac) for stage in stages))
        pools["train"]["legit"][ltype], pools["test"]["legit"][ltype] = list(tr), list(te)
    return pools


def make_call(pool: dict, rng: random.Random, scam_ratio: float = 0.5) -> dict:
    if rng.random() < scam_ratio:
        stype = rng.choice(list(pool["scam"]))
        stages = pool["scam"][stype]
        turns = []
        for i, stage in enumerate(stages):
            if i > 0 and rng.random() < 0.2:  # scammers skip steps
                continue
            for _ in range(1 if rng.random() < 0.75 else 2):
                text, tactics = rng.choice(stage)
                turns.append({"text": _asr_noise(_fill(text, rng), rng), "tactics": tactics})
        return {"label": "scam", "scam_type": stype, "turns": turns}
    ltype = rng.choice(list(pool["legit"]))
    turns = [{"text": _asr_noise(_fill(rng.choice(stage), rng), rng), "tactics": []}
             for stage in pool["legit"][ltype]]
    return {"label": "legit", "scam_type": None, "legit_type": ltype, "turns": turns}


def generate(n: int, seed: int = 7, test_frac: float = 0.25) -> tuple[list[dict], list[dict]]:
    pools = build_pools(seed, test_frac)
    rng = random.Random(seed + 1)
    n_test = int(n * test_frac)
    train = [make_call(pools["train"], rng) for _ in range(n - n_test)]
    test = [make_call(pools["test"], rng) for _ in range(n_test)]
    return train, test


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=4000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", type=Path, default=Path("data/synthetic"))
    args = ap.parse_args()
    train, test = generate(args.n, args.seed)
    args.out.mkdir(parents=True, exist_ok=True)
    for name, calls in (("train", train), ("test", test)):
        with open(args.out / f"{name}.jsonl", "w") as f:
            for c in calls:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"wrote {len(train)} train / {len(test)} test calls to {args.out}")


if __name__ == "__main__":
    main()
