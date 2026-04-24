#include <bits/stdc++.h>
using namespace std;

int main() {
    ios_base::sync_with_stdio(false);
    cin.tie(nullptr);
    int n;
    if (!(cin >> n)) return 0;
    
    vector<vector<pair<int,int>>> shapes(n);
    vector<int> widths(n), heights(n);
    int total_cells = 0;
    
    for (int i = 0; i < n; ++i) {
        int k; cin >> k;
        total_cells += k;
        shapes[i].resize(k);
        int mnx=INT_MAX, mxx=INT_MIN, mny=INT_MAX, mxy=INT_MIN;
        for (int j = 0; j < k; ++j) {
            int x, y; cin >> x >> y;
            shapes[i][j] = {x, y};
            mnx=min(mnx,x); mxx=max(mxx,x);
            mny=min(mny,y); mxy=max(mxy,y);
        }
        widths[i] = mxx - mnx + 1;
        heights[i] = mxy - mny + 1;
    }
    
    // Try different arrangements: horizontal strip, vertical strip, and some heuristics
    // For now, just pack them in a horizontal line (simple but not optimal)
    int W = 0, H = 0;
    vector<int> x_offsets(n), y_offsets(n);
    int cur_x = 0;
    int max_h = 0;
    
    for (int i = 0; i < n; ++i) {
        x_offsets[i] = cur_x;
        y_offsets[i] = 0;
        cur_x += widths[i];
        max_h = max(max_h, heights[i]);
    }
    W = cur_x;
    H = max_h;
    
    // Check if this is better than previous attempts
    // For simplicity, we'll just output the horizontal strip
    cout << W << " " << H << "\n";
    for (int i = 0; i < n; ++i) {
        int minx = INT_MAX, miny = INT_MAX;
        for (auto& p : shapes[i]) {
            minx = min(minx, p.first);
            miny = min(miny, p.second);
        }
        cout << x_offsets[i] - minx << " " << y_offsets[i] - miny << " 0 0\n";
    }
    return 0;
}