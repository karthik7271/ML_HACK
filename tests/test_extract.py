from dadi.extract import extract, normalize_spoken


def test_spoken_phone_number_is_collapsed():
    intel = extract("call me on nine eight seven six five four three two one zero")
    assert intel.phones == {"9876543210"}


def test_double_and_hindi_digits():
    intel = extract("number hai nau aath double seven chhe paanch chaar teen do ek")
    assert intel.phones == {"9877654321"}


def test_devanagari_digits():
    assert "9876543210" in normalize_spoken("मेरा नंबर ९८७६५४३२१० है")


def test_short_digit_words_left_alone():
    assert normalize_spoken("do you have one minute") == "do you have one minute"


def test_spoken_upi_id():
    intel = extract("paise bhejo cbi dot safe at the rate paytm pe")
    assert intel.upi_ids == {"cbi.safe@paytm"}


def test_email_is_not_upi():
    assert extract("mail karo rahul@gmail.com pe").upi_ids == set()


def test_account_ifsc_amount_and_authority():
    intel = extract("Mumbai police se inspector vikram singh, 2 lakh daalo account 503812347761 IFSC SBIN0001234 mein")
    assert intel.accounts == {"503812347761"}
    assert intel.ifsc == {"SBIN0001234"}
    assert "2 lakh" in intel.amounts
    assert intel.authorities == {"Mumbai Police"}
    assert intel.officer_names == {"Vikram Singh"}


def test_phone_with_country_code_is_not_an_account():
    intel = extract("whatsapp karo +91 9988776655 pe")
    assert intel.phones == {"9988776655"}
    assert intel.accounts == set()


def test_merge_returns_only_new_items():
    a = extract("upi verification.cell@ybl")
    new = a.merge(extract("upi verification.cell@ybl aur 9876543210"))
    assert new.upi_ids == set() and new.phones == {"9876543210"}
    assert a.phones == {"9876543210"}


def test_amount_in_words_and_crime_branch():
    intel = extract("mumbai crime branch se, do lakh rupaye bhejiye")
    assert "do lakh" in intel.amounts
    assert "Crime Branch" in intel.authorities
