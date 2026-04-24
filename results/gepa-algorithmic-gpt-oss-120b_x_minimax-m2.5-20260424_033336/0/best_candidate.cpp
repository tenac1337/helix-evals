#include <bits/stdc++.h>
using namespace std;

int main() {
    ios_base::sync_with_stdio(false);
    cin.tie(NULL);
    
    int n;
    if(!(cin >> n)) return 0;
    
    vector<vector<pair<int,int>>> pieces(n);
    vector<int> ks(n);
    
    for (int i = 0; i < n; i++) {
        cin >> ks[i];
        pieces[i].reserve(ks[i]);
        for (int j = 0; j < ks[i]; j++) {
            int x, y;
            cin >> x >> y;
            pieces[i].push_back({x, y});
        }
    }
    
    // Compute bounding boxes for each piece (no rotation/reflection)
    vector<int> width(n), height(n);
    for (int i = 0; i < n; i++) {
        int minx = INT_MAX, maxx = INT_MIN, miny = INT_MAX, maxy = INT_MIN;
        for (auto [x, y] : pieces[i]) {
            minx = min(minx, x);
            maxx = max(maxx, x);
            miny = min(miny, y);
            maxy = max(maxy, y);
        }
        width[i] = maxx - minx + 1;
        height[i] = maxy - miny + 1;
    }
    
    // Place pieces in a column, each at x=0
    long long totalWidth = 0;
    long long totalHeight = 0;
    
    for (int i = 0; i < n; i++) {
        totalWidth = max(totalWidth, (long long)width[i]);
        totalHeight += height[i];
    }
    
    // Add some padding between pieces to avoid edge cases
    long long W = totalWidth + 2;
    long long H = totalHeight + 2;
    
    cout << W << " " << H << "\n";
    
    long long curY = 1;
    for (int i = 0; i < n; i++) {
        // Shift piece to have min coordinates at origin, then translate
        int minx = INT_MAX, miny = INT_MAX;
        for (auto [x, y] : pieces[i]) {
            minx = min(minx, x);
            miny = min(miny, y);
        }
        
        int X = 1 - minx;  // shift so leftmost cell is at x=1
        int Y = curY - miny;  // place at current Y position
        
        cout << X << " " << Y << " 0 0\n";
        
        curY += height[i];
    }
    
    return 0;
}