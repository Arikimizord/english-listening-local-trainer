using System;
using System.Diagnostics;
using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;

namespace ClassroomPlayer {
 // Presentation only: a finite, three-second scene, independent of media state.
 public sealed class LoadingScene : FrameworkElement, IDisposable {
  readonly DispatcherTimer animation=new DispatcherTimer{Interval=TimeSpan.FromMilliseconds(33)};
  readonly Stopwatch elapsed=new Stopwatch();
  BitmapSource[] frames;
  Action completed;
  public LoadingScene(){
   IsHitTestVisible=true;
   using(var stream=typeof(LoadingScene).Assembly.GetManifestResourceStream("CatsFrames")){
    var bitmap=new BitmapImage();bitmap.BeginInit();bitmap.CacheOption=BitmapCacheOption.OnLoad;bitmap.StreamSource=stream;bitmap.EndInit();bitmap.Freeze();
    frames=new BitmapSource[9];for(int i=0;i<9;i++){frames[i]=new CroppedBitmap(bitmap,new Int32Rect(0,i*237,720,237));frames[i].Freeze();}
   }
   animation.Tick+=Animate;
  }
  public void Start(Action done){completed=done;elapsed.Start();animation.Start();InvalidateVisual();}
  void Animate(object sender,EventArgs e){if(elapsed.Elapsed.TotalSeconds>=3){var done=completed;completed=null;animation.Stop();if(done!=null)done();}else InvalidateVisual();}
  public void Dispose(){animation.Stop();animation.Tick-=Animate;elapsed.Stop();completed=null;frames=null;}
  static SolidColorBrush B(string color){var b=(SolidColorBrush)new BrushConverter().ConvertFromString(color);b.Freeze();return b;}
  static void Text(DrawingContext dc,string text,double size,string color,double x,double y){dc.DrawText(new FormattedText(text,System.Globalization.CultureInfo.CurrentUICulture,FlowDirection.LeftToRight,new Typeface("Microsoft YaHei UI"),size,B(color)),new Point(x,y));}
  protected override void OnRender(DrawingContext dc){
   base.OnRender(dc);dc.DrawRectangle(B("#FCF6EE"),null,new Rect(0,0,ActualWidth,ActualHeight));
   double scale=Math.Min(ActualWidth/1000,ActualHeight/620);if(scale<=0)return;
   dc.PushTransform(new TranslateTransform((ActualWidth-1000*scale)/2,(ActualHeight-620*scale)/2));dc.PushTransform(new ScaleTransform(scale,scale));
   dc.DrawRoundedRectangle(B("#327B68"),null,new Rect(406,126,188,34),12,12);Text(dc,"Learn with Adam",18,"#FFFFFF",421,130);
   Text(dc,"听力课堂",36,"#293F3B",422,185);Text(dc,"跟上好奇心，听见每一点进步",16,"#697D76",380,240);
   double t=Math.Min(1,elapsed.Elapsed.TotalSeconds/3);
   // The mouse is the leading edge. The final section lets all three cats clear 100%.
   double catX=-140+1180*t,mouseX=catX+320;
   double progress=Math.Max(0,Math.Min(1,(mouseX-180)/640));
   dc.DrawRoundedRectangle(B("#E3E8DA"),null,new Rect(180,366,640,12),6,6);
   if(progress>0)dc.DrawRoundedRectangle(B("#E6B558"),null,new Rect(180,366,640*progress,12),6,6);
   if(frames!=null)dc.DrawImage(frames[(int)(elapsed.Elapsed.TotalMilliseconds/120)%frames.Length],new Rect(catX,266,300,98.75));
   DrawMouse(dc,mouseX,347+Math.Sin(t*65)*2);
   Text(dc,"0%",13,"#697D76",180,397);Text(dc,"100%",13,"#697D76",785,397);
   Text(dc,((int)(progress*100)).ToString()+"%",23,"#327B68",478,448);
   Text(dc,"小猫正在追赶进度…",14,"#697D76",426,490);
   dc.Pop();dc.Pop();
  }
  static void DrawMouse(DrawingContext dc,double x,double y){
   dc.PushTransform(new TranslateTransform(x,y));
   var outline=new Pen(B("#665B58"),1.7);
   var tail=Geometry.Parse("M -20,0 C -36,-15 -43,12 -52,1");dc.DrawGeometry(null,new Pen(B("#C88D84"),2.5),tail);
   dc.DrawEllipse(B("#ADB6AF"),outline,new Point(-8,0),20,10);
   dc.DrawGeometry(B("#ADB6AF"),outline,Geometry.Parse("M 3,-8 Q 13,-6 23,1 Q 13,9 1,8 Z"));
   dc.DrawEllipse(B("#ADB6AF"),outline,new Point(2,-10),7,9);dc.DrawEllipse(B("#E9B5A8"),null,new Point(2,-10),3.5,5);
   dc.DrawEllipse(B("#293F3B"),null,new Point(13,-2),1.8,1.8);dc.DrawEllipse(B("#C88D84"),null,new Point(23,1),2.5,2);
   dc.DrawLine(outline,new Point(-17,8),new Point(-23,12));dc.DrawLine(outline,new Point(3,8),new Point(10,11));
   dc.DrawLine(new Pen(B("#84746B"),1),new Point(17,3),new Point(29,6));dc.Pop();
  }
 }
}

