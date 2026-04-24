#include <bits/stdc++.h>
using namespace std;

int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    int n;
    if (!(cin >> n)) return 0;

    vector<vector<pair<int,int>>> shapes;
    shapes.reserve(n);
    int maxW = 0, maxH = 0;

    for (int i = 0; i < n; ++i) {
        int k;
        cin >> k;
        vector<pair<int,int>> cells;
        cells.reserve(k);
        int minX = INT_MAX, maxX = INT_MIN;
        int minY = INT_MAX, maxY = INT_MIN;
        for (int j = 0; j < k; ++j) {
            int x, y;
            cin >> x >> y;
            cells.emplace_back(x, y);
            minX = min(minX, x);
            maxX = max(maxX, x);
            minY = min(minY, y);
            maxY = max(maxY, y);
        }
        // normalize to non-negative coordinates
        vector<pair<int,int>> norm;
        norm.reserve(k);
        for (auto &p : cells) {
            norm.emplace_back(p.first - minX, p.second - minY);
        }
        shapes.push_back(move(norm));
        int w = maxX - minX + 1;
        int h = maxY - minY + 1;
        if (w > maxW) maxW = w;
        if (h > maxH) maxH = h;
    }

    long long W = 1LL * n * maxW;
    long long H = maxH;

    cout << W << " " << H << "\n";
    for (int i = 0; i < n; ++i) {
        long long Xi = 1LL * i * maxW;
        long long Yi = 0;
        int Ri = 0;
        int Fi = 0;
        cout << Xi << " " << Yi << " " << Ri << " " << Fi << "\n";
    }

    return 0;
}