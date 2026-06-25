#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <pybind11/stl.h>
#include <opencv2/opencv.hpp>
#include <tesseract/baseapi.h>
#include <string>
#include <vector>
#include <tuple>
#include <optional>
#include <algorithm>

namespace py = pybind11;

std::optional<std::tuple<int, int>> find_element(py::array_t<uint8_t> img_array, const std::string& target_text) {
    // 1. Convert numpy array to cv::Mat
    py::buffer_info buf = img_array.request();
    if (buf.ndim != 3) {
        throw std::runtime_error("Number of dimensions must be 3 (Height, Width, Channels)");
    }
    
    int h = buf.shape[0];
    int w = buf.shape[1];
    int c = buf.shape[2];
    
    cv::Mat img(h, w, (c == 4) ? CV_8UC4 : CV_8UC3, buf.ptr);

    // 2. Pre-processing: Grayscale and Thresholding
    cv::Mat gray, thresh;
    cv::cvtColor(img, gray, (c == 4) ? cv::COLOR_BGRA2GRAY : cv::COLOR_BGR2GRAY);
    cv::threshold(gray, thresh, 0, 255, cv::THRESH_BINARY_INV | cv::THRESH_OTSU);

    // 3. Setup Tesseract API
    tesseract::TessBaseAPI tess;
    if (tess.Init(NULL, "eng", tesseract::OEM_DEFAULT)) {
        throw std::runtime_error("Could not initialize tesseract.");
    }
    tess.SetPageSegMode(tesseract::PSM_SPARSE_TEXT); // psm 11
    tess.SetImage(thresh.data, thresh.cols, thresh.rows, thresh.channels(), thresh.step1());
    tess.Recognize(0);

    // 4. Iterate over results
    tesseract::ResultIterator* ri = tess.GetIterator();
    tesseract::PageIteratorLevel level = tesseract::RIL_WORD;

    std::string target_lower = target_text;
    std::transform(target_lower.begin(), target_lower.end(), target_lower.begin(), ::tolower);

    int best_x = -1, best_y = -1, best_w = -1, best_h = -1;
    bool found = false;

    if (ri != 0) {
        do {
            const char* word = ri->GetUTF8Text(level);
            float conf = ri->Confidence(level);
            if (word != 0 && conf > 30.0) {
                std::string word_str(word);
                delete[] word;
                
                // trim and lower
                word_str.erase(word_str.find_last_not_of(" \n\r\t") + 1);
                std::transform(word_str.begin(), word_str.end(), word_str.begin(), ::tolower);

                if (word_str.empty()) continue;

                if (word_str == target_lower || 
                    (word_str.length() >= 4 && (word_str.find(target_lower) != std::string::npos || target_lower.find(word_str) != std::string::npos))) {
                    ri->BoundingBox(level, &best_x, &best_y, &best_w, &best_h);
                    found = true;
                    break;
                }
            }
        } while (ri->Next(level));
        delete ri;
    }

    tess.End();

    if (found) {
        int center_x = best_x + (best_w - best_x) / 2;
        int center_y = best_y + (best_h - best_y) / 2;
        return std::make_tuple(center_x, center_y);
    }

    return std::nullopt;
}

PYBIND11_MODULE(vision_ext, m) {
    m.doc() = "C++ Vision Extension using OpenCV and Tesseract";
    m.def("find_element", &find_element, "Find element coordinates using OCR");
}
