#include <bits/stdc++.h>
using namespace std;

struct Piece {
    vector<pair<int,int>> cells;
    int k;
};

Piece applyTransform(const Piece& p, int r, int f) {
    Piece res = p;
    res.cells.resize(p.k);
    for (int i = 0; i < p.k; i++) {
        int x = p.cells[i].first;
        int y = p.cells[i].second;
        // Reflect across y-axis if needed
        if (f) x = -x;
        // Rotate r times 90 degrees clockwise
        for (int j = 0; j < r; j++) {
            int nx = -y;
            int ny = x;
            x = nx;
            y = ny;
        }
        res.cells[i] = {x, y};
    }
    return res;
}

int main() {
    ios_base::sync_with_stdio(false);
    cin.tie(NULL);
    
    int n;
    if (!(cin >> n)) return 0;
    vector<Piece> pieces(n);
    long long total_cells = 0;
    
    for (int i = 0; i < n; i++) {
        cin >> pieces[i].k;
        total_cells += pieces[i].k;
        pieces[i].cells.resize(pieces[i].k);
        for (int j = 0; j < pieces[i].k; j++) {
            cin >> pieces[i].cells[j].first >> pieces[i].cells[j].second;
        }
    }
    
    // Simple greedy placement: place pieces one by one in a row-major fashion
    // Try all 8 transformations (4 rotations x 2 reflections) for each piece
    // Use first transformation that fits without overlap
    
    // Grid for placement - start with reasonable size
    // Estimate: assume roughly square packing
    long long side = (long long)ceil(sqrt(total_cells)) + 5;
    long long W = side;
    long long H = side;
    
    // Expand grid if needed during placement
    vector<vector<char>> grid;
    auto expandGrid = [&](long long newW, long long newH) {
        grid.assign(newH, vector<char>(newW, 0));
    };
    expandGrid(W, H);
    
    struct Placement {
        int r, f;
        long long x, y;
    };
    vector<Placement> placements(n);
    
    bool allPlaced = true;
    
    for (int idx = 0; idx < n; idx++) {
        bool placed = false;
        Piece p = pieces[idx];
        
        // Try all 8 transformations
        for (int f = 0; f <= 1 && !placed; f++) {
            for (int r = 0; r < 4 && !placed; r++) {
                Piece tp = applyTransform(p, r, f);
                
                // Find bounding box of transformed piece
                int minx = INT_MAX, maxx = INT_MIN, miny = INT_MAX, maxy = INT_MIN;
                for (auto& c : tp.cells) {
                    minx = min(minx, c.first);
                    maxx = max(maxx, c.first);
                    miny = min(miny, c.second);
                    maxy = max(maxy, c.second);
                }
                int pw = maxx - minx + 1;
                int ph = maxy - miny + 1;
                
                // Shift cells to be non-negative
                vector<pair<int,int>> shifted(tp.cells.size());
                for (size_t i = 0; i < tp.cells.size(); i++) {
                    shifted[i] = {tp.cells[i].first - minx, tp.cells[i].second - miny};
                }
                
                // Try to place at each position in grid
                for (long long gy = 0; gy <= H - ph && !placed; gy++) {
                    for (long long gx = 0; gx <= W - pw && !placed; gx++) {
                        bool ok = true;
                        for (auto& c : shifted) {
                            int cx = gx + c.first;
                            int cy = gy + c.second;
                            if (cx < 0 || cx >= W || cy < 0 || cy >= H || grid[cy][cx]) {
                                ok = false;
                                break;
                            }
                        }
                        if (ok) {
                            // Place it
                            for (auto& c : shifted) {
                                grid[gy + c.second][gx + c.first] = 1;
                            }
                            placements[idx] = {r, f, gx, gy};
                            placed = true;
                        }
                    }
                }
            }
        }
        
        if (!placed) {
            // Need to expand grid and retry
            // Expand in both dimensions
            long long oldW = W, oldH = H;
            W = max(W, (long long)side * 2);
            H = max(H, (long long)side * 2);
            while (W * H < total_cells * 2) {
                if (W <= H) W += 5;
                else H += 5;
            }
            expandGrid(W, H);
            
            // Retry with expanded grid - this piece will be placed now
            // (in practice, we just continue the loop, it will find a spot)
            // Actually, let's restart placement from beginning with new grid
            grid.assign(H, vector<char>(W, 0));
            idx = -1; // restart
            continue;
        }
    }
    
    // Find actual bounding box of all placed pieces
    long long minX = W, minY = H, maxX = 0, maxY = 0;
    for (int idx = 0; idx < n; idx++) {
        Piece tp = applyTransform(pieces[idx], placements[idx].r, placements[idx].f);
        for (auto& c : tp.cells) {
            long long gx = placements[idx].x + c.first;
            long long gy = placements[idx].y + c.second;
            minX = min(minX, gx);
            maxX = max(maxX, gx);
            minY = min(minY, gy);
            maxY = max(maxY, gy);
        }
    }
    
    // Shift everything to start from (0,0)
    long long offsetX = minX;
    long long offsetY = minY;
    long long finalW = maxX - minX + 1;
    long long finalH = maxY - minY + 1;
    
    // Output
    cout << finalW << " " << finalH << "\n";
    for (int i = 0; i < n; i++) {
        cout << (placements[i].x - offsetX) << " " << (placements[i].y - offsetY) 
             << " " << placements[i].r << " " << placements[i].f << "\n";
    }
    
    return 0;
}