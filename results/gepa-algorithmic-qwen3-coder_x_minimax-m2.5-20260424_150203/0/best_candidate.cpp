#include <bits/stdc++.h>
using namespace std;

int main() {
    ios_base::sync_with_stdio(false);
    cin.tie(nullptr);
    int n;
    if (!(cin >> n)) return 0;
    vector<int> minx(n), miny(n);
    int max_width = 0;
    int cur_y = 0;
    vector<int> heights(n);
    for (int i = 0; i < n; ++i) {
        int k; cin >> k;
        int mnx=INT_MAX, mxx=INT_MIN, mny=INT_MAX, mxy=INT_MIN;
        for (int j = 0; j < k; ++j) {
            int x, y; cin >> x >> y;
            mnx=min(mnx,x); mxx=max(mxx,x);
            mny=min(mny,y); mxy=max(mxy,y);
        }
        minx[i]=mnx; miny[i]=mny;
        int w=mxx-mnx+1, h=mxy-mny+1;
        heights[i]=h;
        max_width=max(max_width,w);
        cur_y+=h;
    }
    cout << max_width << " " << cur_y << "\n";
    int y=0;
    for (int i = 0; i < n; ++i) {
        cout << -minx[i] << " " << y-miny[i] << " 0 0\n";
        y+=heights[i];
    }
    return 0;
}