// Use local layout offsets after the composition width is ready.
exports.captionBoundsFromOffsets = (element, rise = 0) => ({
  left: element.offsetLeft, right: element.offsetLeft + element.offsetWidth,
  top: element.offsetTop + rise,
  bottom: element.offsetTop + rise + element.offsetHeight,
  height: element.offsetHeight,
});
