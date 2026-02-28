string reverseString(string s, int n) {
    string result = "";
    int i = n - 1;
    while (i >= 0) {
        result = result + s[i];
        i = i - 1;
    }
    return result;
}

string answer = reverseString("robot", 5);
