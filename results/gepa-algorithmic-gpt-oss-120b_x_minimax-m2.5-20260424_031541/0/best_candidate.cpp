#include <bits/stdc++.h>
using namespace std;

struct Piece {
    vector<pair<int,int>> cells;
    int w, h;
};

int main() {
    ios_base::sync_with_stdio(false);
    cin.tie(NULL);
    
    int n;
    if(!(cin >> n)) return 0;
    
    vector<Piece> pieces(n);
    long long total_cells = 0;
    
    for (int i = 0; i < n; i++) {
        int k;
        cin >> k;
        pieces[i].cells.resize(k);
        for (int j = 0; j < k; j++) {
            cin >> pieces[i].cells[j].first >> pieces[i].cells[j].second;
        }
        total_cells += k;
        
        // Compute bounding box
        int minx = pieces[i].cells[0].first;
        int maxx = pieces[i].cells[0].first;
        int miny = pieces[i].cells[0].second;
        int maxy = pieces[i].cells[0].second;
        for (auto &c : pieces[i].cells) {
            minx = min(minx, c.first);
            maxx = max(maxx, c.first);
            miny = min(miny, c.second);
            maxy = max(maxy, c.second);
        }
        // Normalize to origin
        for (auto &c : pieces[i].cells) {
            c.first -= minx;
            c.second -= miny;
        }
        pieces[i].w = maxx - minx + 1;
        pieces[i].h = maxy - miny + 1;
    }
    
    // Place pieces in a row, one after another
    // Each piece at (offset, 0), no rotation, no reflection
    long long W = 0;
    long long maxH = 0;
    
    // Calculate required dimensions
    for (int i = 0; i < n; i++) {
        W += pieces[i].w;
        maxH = max(maxH, (long long)pieces[i].h);
    }
    
    // Output
    cout << W << " " << maxH << "\n";
    
    long long offset = 0;
    for (int i = 0; i < n; i++) {
        cout << offset << " 0 0 0\n";
        offset += pieces[i].w;
    }
    
    return 0;
}