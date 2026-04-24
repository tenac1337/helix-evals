#include <bits/stdc++.h>
using namespace std;

int main() {
    ios_base::sync_with_stdio(false);
    cin.tie(nullptr);
    int n;
    if (!(cin >> n)) return 0;
    
    vector<vector<pair<int,int>>> pieces(n);
    vector<int> widths(n), heights(n);
    int total_cells = 0;
    
    for (int i = 0; i < n; ++i) {
        int k; cin >> k;
        total_cells += k;
        int mnx=INT_MAX, mxx=INT_MIN, mny=INT_MAX, mxy=INT_MIN;
        pieces[i].resize(k);
        for (int j = 0; j < k; ++j) {
            int x, y; cin >> x >> y;
            pieces[i][j] = {x, y};
            mnx=min(mnx,x); mxx=max(mxx,x);
            mny=min(mny,y); mxy=max(mxy,y);
        }
        widths[i] = mxx - mnx + 1;
        heights[i] = mxy - mny + 1;
    }
    
    // Create all rotations and reflections of each piece
    vector<vector<vector<pair<int,int>>>> all_forms(n);
    for (int i = 0; i < n; ++i) {
        vector<vector<pair<int,int>>> forms;
        vector<pair<int,int>>& shape = pieces[i];
        
        // Original shape
        vector<pair<int,int>> form = shape;
        forms.push_back(form);
        
        // 90° clockwise
        vector<pair<int,int>> form90;
        for (auto& p : shape) {
            form90.push_back({p.second, -p.first});
        }
        forms.push_back(form90);
        
        // 180°
        vector<pair<int,int>> form180;
        for (auto& p : shape) {
            form180.push_back({-p.first, -p.second});
        }
        forms.push_back(form180);
        
        // 270° clockwise
        vector<pair<int,int>> form270;
        for (auto& p : shape) {
            form270.push_back({-p.second, p.first});
        }
        forms.push_back(form270);
        
        // Reflected versions
        for (int r = 0; r < 4; ++r) {
            vector<pair<int,int>> reflected = forms[r];
            for (auto& p : reflected) {
                p.first = -p.first;
            }
            forms.push_back(reflected);
        }
        
        // Normalize each form to start at (0,0)
        for (auto& form : forms) {
            int minx = INT_MAX, miny = INT_MAX;
            for (auto& p : form) {
                minx = min(minx, p.first);
                miny = min(miny, p.second);
            }
            for (auto& p : form) {
                p.first -= minx;
                p.second -= miny;
            }
        }
        
        all_forms[i] = forms;
    }
    
    // Try placing pieces in a grid layout to minimize area
    // Start with a simple greedy approach: try to fit as many pieces as possible in a row
    // Then try to stack rows to minimize height
    
    int best_area = INT_MAX;
    int best_w = 0, best_h = 0;
    vector<pair<int,int>> best_positions(n);
    vector<int> best_rotations(n);
    vector<int> best_flips(n);
    
    // Try different grid dimensions
    for (int rows = 1; rows <= n; ++rows) {
        if (n % rows != 0) continue;
        int cols = n / rows;
        int max_w = 0, max_h = 0;
        
        // For each row, compute the max width and height needed
        vector<int> row_widths(rows, 0);
        vector<int> row_heights(rows, 0);
        
        for (int r = 0; r < rows; ++r) {
            int w = 0, h = 0;
            for (int c = 0; c < cols; ++c) {
                int idx = r * cols + c;
                w += widths[idx];
                h = max(h, heights[idx]);
            }
            row_widths[r] = w;
            row_heights[r] = h;
        }
        
        int total_w = *max_element(row_widths.begin(), row_widths.end());
        int total_h = accumulate(row_heights.begin(), row_heights.end(), 0);
        
        int area = total_w * total_h;
        if (area < best_area) {
            best_area = area;
            best_w = total_w;
            best_h = total_h;
            
            // Place pieces in grid
            int cur_y = 0;
            for (int r = 0; r < rows; ++r) {
                int cur_x = 0;
                for (int c = 0; c < cols; ++c) {
                    int idx = r * cols + c;
                    best_positions[idx] = {cur_x, cur_y};
                    best_rotations[idx] = 0;
                    best_flips[idx] = 0;
                    cur_x += widths[idx];
                }
                cur_y += row_heights[r];
            }
        }
    }
    
    // Also try single row
    {
        int total_w = 0;
        int max_h = 0;
        for (int i = 0; i < n; ++i) {
            total_w += widths[i];
            max_h = max(max_h, heights[i]);
        }
        int area = total_w * max_h;
        if (area < best_area) {
            best_area = area;
            best_w = total_w;
            best_h = max_h;
            
            int cur_x = 0;
            for (int i = 0; i < n; ++i) {
                best_positions[i] = {cur_x, 0};
                best_rotations[i] = 0;
                best_flips[i] = 0;
                cur_x += widths[i];
            }
        }
    }
    
    // Also try single column
    {
        int max_w = 0;
        int total_h = 0;
        for (int i = 0; i < n; ++i) {
            max_w = max(max_w, widths[i]);
            total_h += heights[i];
        }
        int area = max_w * total_h;
        if (area < best_area) {
            best_area = area;
            best_w = max_w;
            best_h = total_h;
            
            int cur_y = 0;
            for (int i = 0; i < n; ++i) {
                best_positions[i] = {0, cur_y};
                best_rotations[i] = 0;
                best_flips[i] = 0;
                cur_y += heights[i];
            }
        }
    }
    
    cout << best_w << " " << best_h << "\n";
    for (int i = 0; i < n; ++i) {
        cout << best_positions[i].first << " " << best_positions[i].second << " " << best_rotations[i] << " " << best_flips[i] << "\n";
    }
    
    return 0;
}